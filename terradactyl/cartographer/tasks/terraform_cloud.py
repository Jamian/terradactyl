import datetime
import os
import json
import logging
import requests
import threading

from celery import shared_task
from django.http import HttpResponse, JsonResponse

from cartographer.gizmo.models import Resource, ResourceInstance, State, Workspace
from cartographer.models import TerraformCloudAPIKey, TerraformCloudOrganization
from cartographer.utils.terraform_cloud import TerraformCloudClient
from cartographer.gizmo.models.exceptions import VertexDoesNotExistException


BASE_URL = 'https://app.terraform.io'

logger = logging.getLogger(__name__)


@shared_task
def sync_resources(workspace_name):
    """Given the Workspace name, fetch all resources for the current revision and create
    a Resource(Vertex) to represent it in the graph database. Each Resourec only stored basic
    metadata like name, resource type. This does not store any other, especially sensitive,
    information about resources.

    TODO : Handle refresh/subdequent calls. Detach / DROP old resources and make new ones on the new, current revision.

    Args
        workspace_name: the name of the Terraform Cloud Workspace to load resources for.
    """
    print(f'Loading resources for workspace: {workspace_name}...')
    tfc_client = TerraformCloudClient()

    workspace = Workspace.vertices.get(name=workspace_name)
    current_revision = workspace.get_current_state_revision()
    resources_info = tfc_client.resources(workspace.organization, workspace_name)
    resources = resources_info['resources']


    print('----------------------------------------------------')
    print(f'Resources for {workspace_name}')
    # First pass, create resources.
    for r_namespace, resource in resources.items():
        r = Resource.vertices.update_or_create(
            name=resource['name'],
            state_id=current_revision.state_id,
            namespace=r_namespace,
            resource_type=resource['resource_type']
        )
        for instance_index_key in resource['instances']:
            # TODO : Do we need to store index namespace as well?
            ri = ResourceInstance.vertices.update_or_create(
                index_key=instance_index_key,
                state_id=current_revision.state_id,
                resource_type=resource['resource_type']
            )
            ri.instance_of(r)
            print(f'Added instance {instance_index_key} to {r_namespace}')

        current_revision.contains(r)
        print(f'Added {r_namespace}')

    # Second pass, create dependencies.
    for r_namespace, resource in resources.items():
        for dependency in [dep for dep in resource['depends_on'] if 'terraform_remote_state' not in dep]:
            r = Resource.vertices.get(name=resource['name'], state_id=current_revision.state_id)
            try:
                dependency_r = Resource.vertices.get(namespace=dependency, state_id=current_revision.state_id)
                r.depends_on(dependency_r)
            except VertexDoesNotExistException:
                print(f'Could not find: {dependency}')

    print('----------------------------------------------------')


@shared_task
def sync_revisions(workspace_name: str, organization_name: str):
    """Async Celery task that calls Terraform Cloud to fetch all State Revisions for a Terraform
    Workspace. For each State version retrieved (an ordered list from oldest to newest) it will
    create a State(Vertex) to represent it and then set then set that it succeeded the State before.

    Args
        workspace_name: the name of the Terraform Workspace to fetch all State revisions for.
        organization_name: the Terraform Organization name to which the workspace belongs.
    """
    logger.debug('Fetching revisions...')
    tfc_client = TerraformCloudClient()
    workspace = Workspace.vertices.get(name=workspace_name, organization=organization_name)
    try:
        current_local_state_id = workspace.get_current_state_revision().state_id
    except VertexDoesNotExistException:
        current_local_state_id = None
    sorted_state_revisions = tfc_client.state_revisions(workspace_name, organization_name, current_local_state_id)
    previous_state = None
    if len(sorted_state_revisions) > 0:
        for state_info in sorted_state_revisions:
            this_state = State.vertices.update_or_create(
                state_id=state_info['state_id'],
                serial=state_info['serial'],
                resource_count=state_info['resource_count'],
                created_at=state_info['created_at'],
                terraform_version=state_info['terraform_version']
            )
            # TODO: Does this break current state or does it work as already exists just updates.
            if previous_state:
                this_state.succeeded(previous_state)
            previous_state = this_state
        total_revisions = len(sorted_state_revisions)
        logger.debug(f'Created {total_revisions} for {workspace_name}...')

@shared_task
def sync_workspace(workspace_name: str, organization_name: str):
    """Calls Terraform Cloud to synchronise a Workspace.
    
    Args
        workspace: the Workspace object to synchronise with the remote in Terraform Cloud.
    """

    tfc_client = TerraformCloudClient()
    workspace = Workspace.vertices.get(name=workspace_name, organization=organization_name)
    remote_workspace_chain_data = tfc_client.chain(workspace_name=workspace.name, organization_name=workspace.organization)
    # First update or create all Vertices in the chain.
    for workspace_id, workspace_info in remote_workspace_chain_data.items():
        chain_workspace = Workspace.vertices.update_or_create(
            name=workspace_info['name'],
            workspace_id=workspace_id,
            organization=workspace_info['organization_name'],
            created_at=workspace_info['created_at']
        )

        if 'current_state' in workspace_info:
            cs = State.vertices.update_or_create(
                state_id=workspace_info['current_state']['state_id'],
                serial=workspace_info['current_state']['serial'],
                resource_count=workspace_info['current_state']['resource_count'],
                terraform_version=workspace_info['current_state']['terraform_version'],
                created_at=workspace_info['current_state']['created_at']
            )
            chain_workspace.has_current_state(cs)

    # Now that the vertices have been updated, we can add or remove any dependencies.
    print('Handling dependencies as we have updated everything...')
    for workspace_id, workspace_info in remote_workspace_chain_data.items():
        updated_dependencies = []
        chain_workspace = Workspace.vertices.get(name=workspace_info['name'], organization=workspace_info['organization_name'])
        current_dependencies = chain_workspace.get_dependencies(redundant_only=False)

        for namespace, dep_info in workspace_info['depends_on'].items():
            try:
                rws = Workspace.vertices.get(name=dep_info['workspace_name'], organization=workspace_info['organization_name'])
                chain_workspace.depends_on(rws, dep_info['redundant'])
                updated_dependencies.append(rws.name)
            except Exception as error:
                logger.error(f'Error creating dependency for: {workspace_id}')

        # Handle any dependencies that have been removed.
        removed_dependencies = list(set(current_dependencies) - set(updated_dependencies))
        for dependency in removed_dependencies:
            ws_to_remove = Workspace.vertices.get(name=dependency)
            logger.debug(f'Removing dependency... {dependency}')
            chain_workspace.remove_dependency(ws_to_remove)

        sync_revisions(workspace_name=workspace_info['name'], organization_name=workspace_info['organization_name'])


@shared_task
def load_workspaces(org_names=[], do_sync_revisions=True, do_sync_resources=True):
    """Calls Terraform Cloud to fetch all Workspaces for the given
    list of org_names or if none provided, all organizations in the database.

    Args
        org_names: list of TerraformCloudOrganization names to load. If empty then all workspaces
                   for all Organizations are loaded.
        do_sync_revisions: if True then all state revisions are loaded for each Workspace.
        do_sync_resources: if True then all resources are loaded for each Workspace's current state (not all states).
    """
    tfc_client = TerraformCloudClient()
    # TODO : Handle name conflicts across ORGS! Currntly only a single org DB works.
    org_workspaces = {}
    if not org_names:
        org_names = [
            org.name for org in TerraformCloudOrganization.objects.all()]

    for org_name in org_names:
        org = TerraformCloudOrganization.objects.get(name=org_name)
        org.refreshing = True
        org.save()
        logger.debug('Fetching workspaces for organization: {org}')
        workspaces = tfc_client.workspaces(org_name)

        for ws_id, workspace in workspaces.items():
            # Create the workspace.
            ws = Workspace.vertices.update_or_create(
                name=workspace['name'],
                workspace_id=ws_id,
                organization=workspace['organization'],
                created_at=workspace['created_at']
            )
            # Add the current revision, old revisions are fetched later.
            if 'current_state' in workspace:
                cs = State.vertices.update_or_create(
                    state_id=workspace['current_state']['state_id'],
                    serial=workspace['current_state']['serial'],
                    resource_count=workspace['current_state']['resource_count'],
                    terraform_version=workspace['current_state']['terraform_version'],
                    created_at=workspace['current_state']['created_at']
                )

                ws.has_current_state(cs)

            if do_sync_revisions:
                sync_revisions.delay(workspace_name=workspace['name'], organization_name=org_name)
            if do_sync_resources:
                sync_resources.delay(workspace_name=workspace['name'])
        org_workspaces = {**org_workspaces, **workspaces}

    logger.debug('Fetching workspaces: creating edges...')
    for ws_id, workspace in org_workspaces.items():
        # TODO : Multi Org support - this needs to handle org name AND ws name or uniqueness.
        ws = Workspace.vertices.get(name=workspace['name'])
        for namespace, workspace_info in workspace['depends_on'].items():
            required_workspace_name = workspace_info['workspace_name']
            try:
                rws = Workspace.vertices.get(name=required_workspace_name, organization=workspace_info['organization'])
                if required_workspace_name != workspace['name']:
                    ws.depends_on(rws, workspace_info['redundant'])
            except Exception as error:
                logger.error(f'Error creating dependency for: {namespace}')

    logger.debug('Finished refresh updates...')
    org.refreshing = False
    org.save()

    # TODO : Handle any deleted terraform workspaces
    current_workspaces = Workspace.vertices.filter(organization=org_name)
    remote_workspaces = org_workspaces.keys()

    logger.debug('Deleted Workspaces: ', list(set(current_workspaces) - set(remote_workspaces)))


