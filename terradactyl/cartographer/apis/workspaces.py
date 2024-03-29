import datetime
import math
import logging

import humanize
import networkx as nx

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse, JsonResponse


from gremlin_python.process.graph_traversal import __, outE, select, valueMap
from gremlin_python.process.traversal import gte, T, Order, TextP

from cartographer.gizmo import Gizmo
from cartographer.gizmo.models import Resource, State, Workspace
from cartographer.utils.terraform_cloud import TerraformCloudClient
from cartographer.gizmo.models.exceptions import VertexDoesNotExistException
from cartographer.tasks.terraform_cloud import sync_workspace


logger = logging.getLogger(__name__)


def _index_for_name(ws_list, ws_name):
    for pos, ws in enumerate(ws_list):
        if ws['name'] == ws_name:
            return pos


@login_required
@require_http_methods(['GET'])
def get_table_workspaces_data(request):
    """Constructs and returns a set of state objects in a format compatible with
    data tables. 
    """

    redundant_deps_str = request.GET.get('redundant-dependencies', '')

    redundant_dependencies = True if redundant_deps_str == 'true' else False

    order_column_index = int(request.GET.get('order[0][column]'))
    length = int(request.GET.get('length'))
    start = int(request.GET.get('start'))
    end = start + length

    search_value = request.GET.get('search[value]')

    base_query = Gizmo().g.V().hasLabel(Workspace.label)
    if search_value:
        base_query = base_query.has('name', TextP.containing(search_value))

    # Handle Redundant Dependencies
    if redundant_dependencies:
        base_query = base_query.project('workspace', 'count').by(valueMap('name', 'organization'))
        base_query = base_query.by(outE('depends_on').has('redundant', 'true').count()).filter_(select('count').is_(gte(1)))
    else:
        base_query = base_query.valueMap('name', 'organization')

    # Handle Ordering
    order_direction = Order.desc if request.GET.get('order[0][dir]') == 'desc' else Order.asc
    order_by_col_index = request.GET.get('order[0][column]')
    order_column_name = request.GET.get(f'columns[{order_by_col_index}][name]')
    base_query = base_query.order().by(order_column_name, order_direction).range_(start, end)

    results = base_query.toList()

    response_data = {
        'recordsTotal': len(results),
        'draw': int(request.GET.get('draw')),
        'data': []
    }

    for r in results:
        if redundant_dependencies:
            response_data['data'].append([r['workspace']['name'], r['workspace']['organization'], r['count']])
        else:
            response_data['data'].append([r['name'], r['organization']])

    return JsonResponse(response_data)


@login_required
@require_http_methods(['GET'])
def get_graph_workspaces_data(request):
    """Constructs and returns the dataset required to populate a graph of states.
    """
    data = {
        'nodes': [],
        'links': []
    }

    # Calculate values for heatmap. Log to remove weight from the outliers, bringing the data closer together
    # makes the heatmap look a lot nicer and brings more value.

    # TODO : Heatmap should be rate of change -
    #           Do something like time since initial creation / number of revisions
    max_serial = State.vertices.max('serial')
    upper_serial_log = math.log(max_serial)

    workspaces = Workspace.vertices.all()
    for ws in workspaces:
        try:
            current_state = ws.get_current_state_revision()
            current_state_serial = current_state.serial
            current_state_terraform_version = current_state.terraform_version
            current_state_resource_count = current_state.resource_count
        except VertexDoesNotExistException:
            current_state_serial = 0
            current_state_terraform_version = 'N/A'
            current_state_resource_count = 0

        heatmap_p = math.log(current_state_serial if current_state_serial > 0 else 1) / upper_serial_log
        data['nodes'].append({
            '_id': ws._id,
            'name': ws.name,
            'group': 1,
            'class': 'state',
            'terraform_version': current_state_terraform_version,
            'serial': current_state_serial,
            'heatmap_p': heatmap_p,
            'dependency_count': ws.get_dependency_count(),
            'resource_count': current_state_resource_count,
            'organization': ws.organization,
            'created_at': humanize_created_at(ws.created_at),
            'last_updated': ws.last_updated
        })

    for i, node in enumerate(data['nodes']):
        # Add non redundanut dependencies
        for name in Workspace.vertices.get(name=node['name']).get_dependencies(redundant=False):
            data['links'].append({
                'source': i,
                'target': _index_for_name(data['nodes'], name),
                'redundant': 'false',
                'value': 1,
                'type': 'depends_on'
            })
        # Add redundant dependencies
        for name in Workspace.vertices.get(name=node['name']).get_dependencies(redundant=True):
            data['links'].append({
                'source': i,
                'target': _index_for_name(data['nodes'], name),
                'redundant': 'true',
                'value': 1,
                'type': 'depends_on'
            })

    return JsonResponse(data)


@login_required
@require_http_methods(['GET'])
def get_workspace_resources(request, workspace_name):
    is_refresh_str = request.GET.get('refresh')
    is_refresh = True if is_refresh_str == 'true' else False

    include_deps_str = request.GET.get('dependencies')
    include_deps = True if include_deps_str == 'true' else False

    if is_refresh:
        tfc_client = TerraformCloudClient()

        workspace = Workspace.vertices.get(name=workspace_name)
        resources = tfc_client.resources(workspace.organization, workspace.name)

        # First pass, create resources.
        for r_namespace, resource in resources.items():
            r = Resource.vertices.update_or_create(
                name=resource['name'],
                state_id=workspace.workspace_id,
                namespace=r_namespace,
                resource_type=resource['resource_type']
            )
            workspace.contains(r)

        # Second pass, create dependencies.
        for r_namespace, resource in resources.items():
            for dependency in [dep for dep in resource['depends_on'] if 'terraform_remote_state' not in dep]:
                r = Resource.vertices.get(namespace=resource['r_namespace'], state_id=workspace.workspace_id)

                dependency_r = Resource.vertices.get(namespace=dependency, state_id=workspace.workspace_id)
                r.depends_on(dependency_r)

    data = {
        'nodes': [],
        'links': []
    }

    # Fetch the main state resources
    ws = Workspace.vertices.get(name=workspace_name)
    resources = ws.get_resources()
    for r in resources:
        data['nodes'].append({
            '_id': r._id,
            'name': r.name,
            'namespace': r.namespace,
            'resource_type': r.resource_type,
            'state_id': r.state_id,
            'class': 'resource',
            'last_updated': r.last_updated
        })

    if include_deps:
        # Fetch dependency state resources
        dependencies = ws.get_dependencies()
        for dep_name in dependencies:
            dep_ws = Workspace.vertices.get(name=dep_name, organization=ws.organization)
            dep_resources = dep_ws.get_resources()
            for dr in dep_resources:
                data['nodes'].append({
                        '_id': dr._id,
                        'name': dr.name,
                        'namespace': dr.namespace,
                        'resource_type': dr.resource_type,
                        'state_id': dr.state_id,
                        'class': 'resource',
                        'last_updated': dr.last_updated
                    })

    for i, node in enumerate(data['nodes']):
        for name in Resource.vertices.get(name=node['name']).get_dependencies():
            # Handle local dependencies
            data['links'].append({
                'source': i,
                'target': _index_for_name(data['nodes'], name),
                'value': 1,
                'type': 'depends_on'
            })

    response = JsonResponse(data)

    return response


def humanize_created_at(created_at_raw):
    if type(created_at_raw) == str:
        try:
            created_at_raw = float(created_at_raw)
            humanized = humanize.naturaldate(datetime.datetime.fromtimestamp(created_at_raw))
        except ValueError:
            humanized = created_at_raw
    else:
        humanized = humanize.naturaldate(datetime.datetime.fromtimestamp(created_at_raw))

    return humanized


@login_required
@require_http_methods(['GET'])
def get_workspace_run_order(request, workspace_name):
    data = {'nodes': [], 'links': []}
    ws = Workspace.vertices.get(name=workspace_name)
    chain = ws.get_chain()

    workspaces_data = {}
    dependency_counts = {}
    for path in chain[1:]:
        edge_indices = []
        for i, part in enumerate(path):
            if part[T.label] == 'depends_on':
                edge_indices.append(i)
        for i in edge_indices:
            ws_name = path[i+1]['name'][0]
            dep_name = path[i-1]['name'][0]
            if ws_name not in workspaces_data:
                # If the workspace isn't in the data, add it with a required by: dependency
                try:
                    ws_state = Workspace.vertices.get(name=ws_name, organization=path[i+1]['organization'][0]).get_current_state_revision()
                except VertexDoesNotExistException as error:
                    logger.error(f'Unable to generate run order. Dependency in chain missing current state revision - {ws_name}')
                    # TODO : We should return an error to the front end here and no display the graph - or  at least a warning.

                dep_ws = Workspace.vertices.get(name=dep_name, organization=path[i-1]['organization'][0])
                dep_state = dep_ws.get_current_state_revision()
                workspaces_data[ws_name] = {
                    'required_by': [dep_name],
                    'depends_on': [],
                    'workspace_id': path[i+1]['workspace_id'],
                    'terraform_version': ws_state.terraform_version,
                    'organization': ws.organization,
                    'serial': ws_state.serial,
                    'created_at': humanize_created_at(path[i-1]['created_at'][0]),
                    'resource_count': ws_state.resource_count
                }
            else:
                if dep_name not in workspaces_data[ws_name]['required_by']:
                    workspaces_data[ws_name]['required_by'].append(dep_name)

            if dep_name not in workspaces_data:
                workspaces_data[dep_name] = {
                    'required_by': [],
                    'depends_on': [ws_name],
                    'workspace_id': path[i-1]['workspace_id'],
                    'terraform_version': dep_state.terraform_version,
                    'organization': dep_ws.organization,
                    'serial': dep_state.serial,
                    'created_at': humanize_created_at(path[i-1]['created_at'][0]),
                    'resource_count': dep_state.resource_count
                }
                dependency_counts[dep_name] = 1
            else:
                if ws_name not in workspaces_data[dep_name]['depends_on']:
                    workspaces_data[dep_name]['depends_on'].append(ws_name)
                    if dep_name not in dependency_counts:
                        dependency_counts[dep_name] = 1
                    else:
                        dependency_counts[dep_name] += 1

    # Identify any dependency cycles...
    for workspace in workspaces_data:
        cyclic_dependencies = set(workspaces_data[workspace]['depends_on']) & set(
            workspaces_data[workspace]['required_by'])
        if cyclic_dependencies:
            for cyclic_dep in cyclic_dependencies:
                # Handle this side of the cyclic dependency.
                if 'cyclic-dependencies' not in workspaces_data[cyclic_dep]:
                    workspaces_data[workspace]['depends_on'].remove(cyclic_dep)
                if 'cyclic-dependencies' not in workspaces_data[workspace]:
                    workspaces_data[workspace]['cyclic-dependencies'] = [{
                        'name': cyclic_dep,
                        'required_by': workspace
                    }]
                else:
                    workspaces_data[workspace]['cyclic-dependencies'].append({
                        'name': cyclic_dep,
                        'required_by': workspace
                    })

    workspace_dependencies = {ws: workspaces_data[ws]['depends_on'] for ws in workspaces_data}
    G = nx.DiGraph(workspace_dependencies)
    H = nx.path_graph(workspace_dependencies)
    G.add_nodes_from(H)
    run_order = list(reversed(list(nx.topological_sort(G))))

    # Fromate the data block that d3 will use, create nodes and links.
    for i, workspace in enumerate(run_order):
        d_count = dependency_counts[workspace] if workspace in dependency_counts else 0
        if workspace not in [ws['name'] for ws in data['nodes']]:
            data['nodes'].append({
                'workspace_id': workspaces_data[workspace]['workspace_id'],
                'name': workspace,
                'depends_on': workspaces_data[workspace]['depends_on'],
                'terraform_version': workspaces_data[workspace]['terraform_version'],
                'organization': workspaces_data[workspace]['organization'],
                'resource_count': workspaces_data[workspace]['resource_count'],
                'dependency_count': d_count,
                'serial': workspaces_data[workspace]['serial'],
                'created_at': humanize_created_at(workspaces_data[workspace]['created_at']),
                'group': 1,
                'class': 'state'
            })
        if 0 <= i < len(run_order) - 1:
            data['links'].append({
                'source': i,
                'target': i + 1,
                'value': 1,
                'type': 'depends_on'
            })

        if 'cyclic-dependencies' in workspaces_data[workspace]:
            # If first node has dependency (in event of cycles).
            # TODO : Does this break cyclic deps in the middle of the chain?
            for cyclic_dep in workspaces_data[workspace]['cyclic-dependencies']:
                # Get the position of the cyclic dependency node
                cyclic_dep_name = cyclic_dep['name']
                if cyclic_dep_name not in [ws['name'] for ws in data['nodes']]:
                    data['nodes'].append({
                        'workspace_id': workspaces_data[cyclic_dep_name]['workspace_id'],
                        'name': cyclic_dep_name,
                        'depends_on': workspaces_data[cyclic_dep_name]['depends_on'],
                        'terraform_version': workspaces_data[cyclic_dep_name]['terraform_version'],
                        'organization': workspaces_data[cyclic_dep_name]['organization'],
                        'resource_count': workspaces_data[cyclic_dep_name]['resource_count'],
                        'created_at': humanize_created_at(workspaces_data[cyclic_dep_name]['created_at']),
                        'dependency_count': dependency_counts[cyclic_dep_name],
                        'group': 1,
                        'class': 'state'
                    })

                origin_node_pos = _index_for_name(data['nodes'], cyclic_dep['required_by'])
                cyclic_node_pos = _index_for_name(data['nodes'], cyclic_dep['name'])

                data['links'].append({
                    'source': cyclic_node_pos,
                    'target': origin_node_pos,
                    'value': 1,
                    'type': 'depends_on'
                })

    return JsonResponse(data)


@login_required
@require_http_methods(['GET'])
def get_workspace(request, workspace_name):
    data = {'nodes': [], 'links': []}

    is_sync_str = request.GET.get('sync')
    is_sync = True if is_sync_str == 'true' else False

    ws = Workspace.vertices.get(name=workspace_name)
    # TODO : This url should be {org}/{workspace}
    if is_sync:
        sync_workspace.delay({
            'name': ws.name,
            'organization': ws.organization,
            'id': ws.workspace_id,
            'created_at': ws.created_at
        })
        response = HttpResponse()
    else:
        chain = ws.get_chain()
        added_edge_ids = []   # Keep track of added edge IDs to prevent duplication.
        for path in chain[1:]:
            edge_indices = {}
            for i, part in enumerate(path):
                if part[T.label] == 'depends_on':
                    edge_indices[i] = {'id': part[T.id], 'redundant': part['redundant']}
            for i, edge_info in edge_indices.items():
                source_ws = Workspace.vertices.get(name=path[i-1]['name'][0], organization=path[i-1]['organization'][0])
                source_state = source_ws.get_current_state_revision()
                source_index = _insert_dict(data['nodes'], {
                    '_id': path[i-1][T.id],
                    'name': path[i-1]['name'][0],
                    'terraform_version': source_state.terraform_version,
                    'organization': source_ws.organization,
                    'serial': source_state.serial,
                    'dependency_count': Workspace.vertices.get(name=path[i-1]['name'][0]).get_dependency_count(),
                    'resource_count': source_state.resource_count,
                    'created_at': humanize_created_at(path[i-1]['created_at'][0]),
                    'group': 1,
                    'class': 'state'
                })
                
                taget_ws = Workspace.vertices.get(name=path[i-1]['name'][0], organization=path[i-1]['organization'][0])
                target_state = taget_ws.get_current_state_revision()

                target_index = _insert_dict(data['nodes'], {
                    '_id': path[i+1][T.id],
                    'name': path[i+1]['name'][0],
                    'terraform_version': target_state.terraform_version,
                    'organization': taget_ws.organization,
                    'serial': target_state.serial,
                    'dependency_count': Workspace.vertices.get(name=path[i+1]['name'][0]).get_dependency_count(),
                    'resource_count': target_state.resource_count,
                    'created_at': humanize_created_at(path[i+1]['created_at'][0]),
                    'group': 1,
                    'class': 'state'
                })
                if edge_info['id'] not in added_edge_ids:
                    data['links'].append({
                        'source': source_index,
                        'target': target_index,
                        'redundant': edge_info['redundant'],
                        'value': 1,
                        'type': 'depends_on'
                    })
                    added_edge_ids.append(edge_info['id'])

        response = JsonResponse(data)
    return response


def _insert_dict(l, d):
    for i, ld in enumerate(l):
        if ld['name'] == d['name']:
            return i

    l.append(d)
    return len(l)-1
