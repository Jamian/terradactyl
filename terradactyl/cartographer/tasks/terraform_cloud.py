import datetime
import logging

from celery import group, shared_task
from celery.result import AsyncResult

from cartographer.gizmo.models import Resource, ResourceInstance, State, Workspace
from cartographer.models import TerraformCloudOrganization, OrganizationSyncJob
from cartographer.utils.terraform_cloud import TerraformCloudClient, WorkspaceNotFoundException
from cartographer.gizmo.models.exceptions import VertexDoesNotExistException

BASE_URL = 'https://app.terraform.io'

logger = logging.getLogger(__name__)

@shared_task
def sync_organization(org_name: str):
    """For a given organization, fetch all Workspaces and create relevent nodes in the Graph Database. Once
    all nodes are created ensure that dependency edges are created.

    Args:
        org_name (str): The name of the Organization to import all Workspaces for.
    """

    org = TerraformCloudOrganization.objects.get(name=org_name)
    tfc_client = TerraformCloudClient(api_key=org.api_key.value)
    org.save()

    # TODO : Check no other sync job in progress. If there is - fail.
    sync_org_job = OrganizationSyncJob.objects.create(state=OrganizationSyncJob.FETCHING_REMOTE_WORKSPACES, organization=org)
    sync_org_job.started_at = datetime.datetime.now()
    sync_org_job.save()

    workspaces = tfc_client.workspaces(org_name)

    sync_org_job.state = OrganizationSyncJob.DRAWING_LOCAL_GRAPH
    sync_org_job.total_workspaces=len(workspaces)
    sync_org_job.save()
    
    sync_workspace_tasks = group(sync_workspace.s(workspace, sync_org_job.id).set(task_id=f'sync-workspace:' + workspace['name']) for workspace in workspaces)
    result = sync_workspace_tasks.apply_async()

    while not result.ready():
        continue

    sync_org_job.state = OrganizationSyncJob.IMPORTING_STATE_HISTORY
    sync_org_job.save()


    sync_revisions_tasks = group(sync_revisions.s(workspace_name=workspace['name'], organization_name=org_name, initial_run=True)
                                 .set(task_id=f'sync-revisions:' + workspace['name']) for workspace in workspaces)

    result = sync_revisions_tasks.apply_async()

    while not result.ready():
        continue

    sync_org_job.state = OrganizationSyncJob.IMPORTING_RESOURCES
    sync_org_job.save()

    sync_resources_tasks = group(sync_resources.s(workspace_name=workspace['name'], organization_name=org_name).set(task_id=f'sync-resources:' + workspace['name']) for workspace in workspaces)
    result = sync_resources_tasks.apply_async()

    while not result.ready():
        continue

    sync_org_job.finished_at = datetime.datetime.now()
    sync_org_job.state = OrganizationSyncJob.COMPLETE
    sync_org_job.save()

    logger.info('Sync Organization - All Workspace Nodes Created!')   # TODO : Handle Deletion

@shared_task
def sync_resources(workspace_name, organization_name):
    """Given the Workspace name, fetch all resources for the current revision and create
    a Resource(Vertex) to represent it in the graph database. Each Resourec only stored basic
    metadata like name, resource type. This does not store any other, especially sensitive,
    information about resources.

    TODO : Handle refresh/subdequent calls. Detach / DROP old resources and make new ones on the new, current revision.

    Args
        workspace_name: the name of the Terraform Cloud Workspace to load resources for.
    """
    logger.info(f'Loading resources for workspace: {workspace_name}...')
    organization = TerraformCloudOrganization.objects.get(name=organization_name)
    tfc_client = TerraformCloudClient(api_key=organization.api_key.value)

    workspace = Workspace.vertices.get(name=workspace_name)
    current_revision = workspace.get_current_state_revision()
    resources_info = tfc_client.resources(workspace.organization, workspace_name)
    resources = resources_info['resources']

    logger.debug(f'Handling resources for {workspace_name}')
    # First pass, create resources.
    for r_namespace, resource in resources.items():
        r = Resource.vertices.update_or_create(
            name=resource['name'],
            state_id=current_revision.state_id,
            namespace=r_namespace,
            mode=resource['mode'],
            resource_type=resource['resource_type']
        )

        for instance in resource['instances']:
            ri = ResourceInstance.vertices.update_or_create(
                index_key=instance['index_key'],
                iid=instance['iid'],
                state_id=current_revision.state_id,
                resource_type=resource['resource_type']
            )
            logger.debug(f'Adding instance {instance["iid"]} to {r.namespace}')
            ri.instance_of(r)

        current_revision.contains(r)

    # Second pass, create dependencies.
    # TODO : Turn this back on - it's just too much to handle locally. DB becomes way too complex.
    # for r_namespace, resource in resources.items():
    #     try:
    #         source_r = Resource.vertices.get(name=resource['name'], namespace=r_namespace, resource_type=resource['resource_type'], state_id=current_revision.state_id)
    #     except VertexDoesNotExistException:
    #         logger.warning(f'Unable to find resource {r_namespace} so no dependencies added.')
    #         continue
    #     for dependency in [dep for dep in resource['depends_on'] if 'terraform_remote_state' not in dep]:
    #         try:
    #             dependency_r = Resource.vertices.get(namespace=dependency, state_id=current_revision.state_id)
    #             source_r.depends_on(dependency_r)
    #         except VertexDoesNotExistException:
    #             logger.warning(f'Could not find: {dependency} for {r_namespace} in {workspace_name}')

    logger.info(f'Finished processing resources for {workspace_name}')


@shared_task
def sync_revisions(workspace_name, organization_name, initial_run):
    """Async Celery task that calls Terraform Cloud to fetch all State Revisions for a Terraform
    Workspace. For each State version retrieved (an ordered list from oldest to newest) it will
    create a State(Vertex) to represent it and then set then set that it succeeded the State before.

    Args
        workspace_name: the name of the Workspace to sync.
        organization_name: the organization which the workspace belongs to.
        initial_run: whether the import is the initial import.
    """
    
    organization = TerraformCloudOrganization.objects.get(name=organization_name)
    tfc_client = TerraformCloudClient(api_key=organization.api_key.value)

    logger.info(f'Fetching revisions for workspace {workspace_name}...')

    workspace = Workspace.vertices.get(name=workspace_name, organization=organization_name)

    try:
        current_local_state_id = workspace.get_current_state_revision().state_id
    except VertexDoesNotExistException:
        current_local_state_id = None

    sorted_state_revisions = tfc_client.state_revisions(workspace.name, workspace.organization, current_local_state_id, initial_run)
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
        logger.info(f'Created {total_revisions} revisions for {workspace_name}...')


@shared_task(bind=True, max_retries=50, default_retry_delay=6)
def sync_workspace(self, workspace_info, sync_org_job_id=None):
    """Fetches the most up to date Workspace from the remote and syncs any state changes or
    changes to dependencies.

    Args:
        workspace_info (dict): the dict containing Workspace information.
            {
                'name': 'foo',
                'organization': 'bar',
                'created_at': 123456,
                'id': 'workspaceid'
            }
        sync_org_job_id (str): the unique id for the sync job.
    """
    organization = TerraformCloudOrganization.objects.get(name=workspace_info['organization'])
    if sync_org_job_id:
        sync_org_job = OrganizationSyncJob.objects.get(id=sync_org_job_id)   # TODO : Handle does not exist
    tfc_client = TerraformCloudClient(api_key=organization.api_key.value)

    workspace_name = workspace_info['name']

    workspace_dict = tfc_client.workspace(workspace_name, workspace_info['organization'])

    # Create the workspace.
    ws = Workspace.vertices.update_or_create(
        name=workspace_name,
        workspace_id=workspace_info['id'],
        organization=workspace_info['organization'],
        created_at=workspace_info['created_at']
    )

    # Add the current revision, old revisions are fetched later.
    if 'current_state' in workspace_dict:
        cs = State.vertices.update_or_create(
            state_id=workspace_dict['current_state']['state_id'],
            serial=workspace_dict['current_state']['serial'],
            resource_count=workspace_dict['current_state']['resource_count'],
            terraform_version=workspace_dict['current_state']['terraform_version'],
            created_at=workspace_dict['current_state']['created_at']
        )

        ws.has_current_state(cs)

    logger.debug('Fetching workspaces: creating edges...')

    retry=False

    if 'depends_on' in workspace_dict:
        broken_dependencies = []

        for _, dependency_info in workspace_dict['depends_on'].items():
            required_workspace_name = dependency_info['workspace_name']
            # Try to fetch the required dependency and if it doesn't exist - make a lightweight version of it.
            if required_workspace_name != workspace_dict['name']:
                try:
                    rws = Workspace.vertices.get(name=required_workspace_name, organization=dependency_info['organization'])
                    ws.depends_on(rws, lookup_type=dependency_info['lookup_type'], redundant=dependency_info['redundant'])
                except VertexDoesNotExistException:
                    res = AsyncResult(f'sync-workspace:' + required_workspace_name)
                    if not res.ready():
                        # This is overkill, will iterate over all dependencies even if only one isn't there.
                        logger.info(f'Vertex did not exist for dependency {required_workspace_name} in {workspace_name}, sync job status for that workspace is {res.state}.')
                        broken_dependencies.append({'name': required_workspace_name, 'organization': dependency_info['organization']})
                        # Set retry to True so we do, but continue to try and make any other dependencies.
                        retry=True
                        continue
                    elif res.state == 'SUCCESS':
                        # Occasionally this will happen.
                        try:
                            # TODO : We need to handle broken dependencies - Workspace depends on a Workspace which no longer exists.
                            rws = Workspace.vertices.get(name=required_workspace_name, organization=dependency_info['organization'])
                            ws.depends_on(rws, lookup_type=dependency_info['lookup_type'], redundant=dependency_info['redundant'])
                        except VertexDoesNotExistException:
                            logger.warning(f'Vertex did not exist for dependency {required_workspace_name} in {workspace_name}, despite successful job run.')
                            broken_dependencies.append({'name': required_workspace_name, 'organization': dependency_info['organization']})
                    else:
                        logger.error(f'Could not create dependency {required_workspace_name} for {workspace_name}. Sync job status is {res.state}.')


    if sync_org_job_id:
        # When a full organisation sync we can get broken Workspaces with bad dep links.
        if self.request.retries == self.max_retries:
            # We're out of retries, just quickly check if we have any broken dependencies.
            current_workspaces = Workspace.vertices.count()
            expected_workspaces = sync_org_job.total_workspaces
            
            if current_workspaces == expected_workspaces:
                # Handle dependencies that did not exist?
                # Add list to the Vertex some how so we can see it in the GraphDB?
                for broken_dependency in broken_dependencies:
                    try:
                        tfc_client.workspace(broken_dependency['name'], broken_dependency['organization'])
                        logger.error(f'Dependency {broken_dependency["name"]} has not been created locally, but it does exist on the remote.')
                    except WorkspaceNotFoundException:
                        logger.error(f'Dependency {broken_dependency["name"]} does not exist. Has the Workspace been deleted?')
    else:
        if retry:
            self.retry()
