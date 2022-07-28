import datetime
import json

from collections import OrderedDict

import humanize

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from cartographer.gizmo import Gizmo
from cartographer.gizmo.models import Resource, ResourceInstance, Workspace
from cartographer.gizmo.models.exceptions import VertexDoesNotExistException


@login_required
@require_http_methods(['GET'])
def index(request):
    """Main entrypoint post login into the system.
    """
    if not request.user.is_authenticated:
        return redirect('%s?next=%s' % (settings.LOGIN_URL, request.path))

    context = {
        'stats': {
            'state_count': Workspace.vertices.count(),
            'dependency_count': Gizmo().count_edges('depends_on'),
            'redundant_dependency_count': Gizmo().count_edges('depends_on', redundant='true')
        }
    }

    return render(request, 'index.html', context)


@login_required
@require_http_methods(['GET'])
def state(request, state_name):
    """View for showing information about an individual State. Shows basic statistics
    liek resource counts, age etc. APIs are called post load to fetch the network
    graphs and run orders.

    Args
        state_name: the name of the state being viewed
    """
    workspace = Workspace.vertices.get(name=state_name)

    charts_data_growth, _ = _generate_growth_chart_data([workspace], calculate_cumsum=False)
    current_revision = workspace.get_current_state_revision()

    resource_type_dist = Resource.vertices.count_by(group_by='resource_type', state_id=current_revision.state_id)
    sorted_resource_type_dist = dict(sorted(resource_type_dist.items(), key=lambda item: item[1], reverse=True)) 
    charts_data_resource_distribution = {
        'data': json.dumps([d for d in sorted_resource_type_dist.values()]),
        'labels': json.dumps([k for k in sorted_resource_type_dist.keys()])
    }

    downstreams = workspace.get_dependencies()
    redundant_downstreams = workspace.get_dependencies(redundant=True)
    downstream_dependencies = [{'name': d, 'required': ('false' if d in redundant_downstreams else 'true')} for d in downstreams]

    upstreams = workspace.get_upstreams()
    redundant_upstreams = workspace.get_upstreams(redundant=True)
    upstream_dependencies = [{'name': d, 'required': 'false' if d in redundant_upstreams else 'true'} for d in upstreams]

    context = {
        'state_name': state_name,
        'organization': workspace.organization,
        'downstream_dependencies': downstream_dependencies,
        'upstream_dependencies': upstream_dependencies,
        'stats': {
            'latest_apply': humanize.naturaldate(current_revision.created_at_dt) + ' (' + humanize.naturaltime(current_revision.created_at_dt) + ')',
            'resource_count': current_revision.resource_count,
            'last_updated': datetime.datetime.utcfromtimestamp(float(workspace.last_updated)),
            'revision_count': workspace.get_total_revision_count(),
            'created_at': humanize.naturaldate(datetime.datetime.fromtimestamp(workspace.created_at)) + ' (' + humanize.naturaltime(datetime.datetime.fromtimestamp(workspace.created_at)) + ')',
            'terraform_version': current_revision.terraform_version
        },
        'charts': {
            'resource_distribution': charts_data_resource_distribution,
            'growth': charts_data_growth
        }
    }
    return render(request, 'state.html', context)


@login_required
@require_http_methods(['GET'])
def states(request):
    """View for the main network page that visualizes and allows users to explore their whole State network.
    APIs are called post load for fetching the actual network. Initial load does populate the
    page with basic statistics like growth over time, total states and dependencies.
    """
    terraform_version_dist = Workspace.vertices.count_by_current_rev('terraform_version')
    charts_data_terraform_versions = {   # TODO : Does this maintain the order?
        'data': json.dumps([d for d in terraform_version_dist.values()]),
        'labels': json.dumps([k for k in terraform_version_dist.keys()])
    }

    resource_type_dist = ResourceInstance.vertices.count_by('resource_type')
    resource_type_dist['terraform_remote_state'] = 0
    sorted_resource_type_dist = dict(sorted(resource_type_dist.items(), key=lambda item: item[1], reverse=True)) 
    charts_data_resource_distribution = {
        'data': json.dumps([d for d in sorted_resource_type_dist.values()]),
        'labels': json.dumps([k for k in sorted_resource_type_dist.keys()])
    }

    # workspaces = Workspace.vertices.all()
    # FIXME : This now takes too long to do, pull it out into an API?
    charts_data_growth, resource_count = {
        'data': [],
        'labels': []
    }, ResourceInstance.vertices.count()  # TODO : This needs to exclude terraform_remote_state?

    return render(request, 'states.html', {
        'stats': {
            'state_count': Workspace.vertices.count(),
            'dependency_count': Gizmo().count_edges('depends_on'),
            'resource_count': resource_count,
            'resource_type_count': len(resource_type_dist.keys())
        },
        'charts': {
            'terraform_versions': charts_data_terraform_versions,
            'resource_distribution': charts_data_resource_distribution,
            'growth': charts_data_growth
        }})


def index_for_name(ws_list, ws_name):
    for pos, ws in enumerate(ws_list):
        if ws['name'] == ws_name:
            return pos


def insert_dict(l, d):
    for i, ld in enumerate(l):
        if ld == d:
            return i

    l.append(d)
    return len(l)-1


def _generate_growth_chart_data(workspaces, calculate_cumsum=True):
    """Generate growth data for the growth chat by inspecting all revisions for
    either a given, or all workspaces.

    Iterates over revisions and stores the resource count against the date.
    For the first revision, stores the full resource count.
    Following revisions store the difference.
    This allows a cumsum without re-counting existing resources each iteration.

    Args
        workspaces: list of Workspace objects to generate growth data for.
        calculate_cumsum: if True then a cumulatitive sum is calculated. This is required when
                          handling multiple Workspaces.

    Returns
        The data and labels and a resource count.
    """
    charts_growth_data = {}
    resource_count = 0
    for workspace in workspaces:
        has_current_revision = True
        try:
            current_revision = workspace.get_current_state_revision()
        except VertexDoesNotExistException:
            has_current_revision = False

        state_revisions = workspace.get_state_revisions() if has_current_revision else []

        if has_current_revision:
            resource_count += current_revision.resource_count

        prev_resource_count = 0
        # First, for each workspace state revision store the difference on that day.
        # Then we can use those diffs to calculate a cumsum for each day accross as state revisions?
        for state_revision in state_revisions:
            created_at = state_revision.created_at_dt
            count_diff = state_revision.resource_count - prev_resource_count
            if created_at not in charts_growth_data:
                # The first state here is the original, so we add all the resources.
                charts_growth_data[created_at] = count_diff if calculate_cumsum else state_revision.resource_count
            else:
                if calculate_cumsum:
                    charts_growth_data[created_at] += count_diff
                else:
                    charts_growth_data[created_at] = state_revision.resource_count
            prev_resource_count = state_revision.resource_count

        if has_current_revision:
            # Handle current revision resource count (not returned by get revisions right now...)
            count_diff = current_revision.resource_count - prev_resource_count
            current_rev_dt = current_revision.created_at_dt
            if current_rev_dt not in charts_growth_data:
                charts_growth_data[current_rev_dt] = count_diff if calculate_cumsum else current_revision.resource_count
            else:
                if calculate_cumsum:
                    charts_growth_data[current_rev_dt] += count_diff
                else:
                    charts_growth_data[current_rev_dt] = current_revision.resource_count

    if workspaces:
        # Order it
        sorted_charts_growth_data = OrderedDict(sorted(charts_growth_data.items()))

        if calculate_cumsum:
            cumsum = 0
            for k, v in sorted_charts_growth_data.items():
                cumsum += v
                sorted_charts_growth_data[k] = cumsum
    else:
        sorted_charts_growth_data = {}

    charts_data_growth = {
        'data': json.dumps([d for d in sorted_charts_growth_data.values()]),
        'labels': json.dumps([datetime.datetime.strftime(k, '%d %b %Y') for k in sorted_charts_growth_data.keys()])
    }

    return charts_data_growth, resource_count