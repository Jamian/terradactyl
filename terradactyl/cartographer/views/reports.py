from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from cartographer.gizmo import Gizmo
from cartographer.gizmo.models import Workspace
from cartographer.gizmo.models.exceptions import VertexDoesNotExistException


@login_required
def terraform_versions(request):
    """
    """
    workspace_data = []
    workspace_vertices = Workspace.vertices.all()

    for w in workspace_vertices:
        try:
            terraform_version = w.get_current_state_revision().terraform_version
        except VertexDoesNotExistException:
            terraform_version = 'N/A'
        workspace_data.append({
            'name': w.name,
            'org_name': w.organization,
            'terraform_version': terraform_version
        })

    context = {
        'stats': {
        },
        'workspace_data': workspace_data
    }
    return render(request, 'terraform-versions.html', context)

@login_required
def redundant_dependencies(request):
    ""
    ""

    context = {
        'stats': {
            'redundant_count': Gizmo().count_edges('depends_on', redundant='true')
        }
    }

    return render(request, 'redundant-dependencies.html', context)