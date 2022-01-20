import datetime
import os
import pytz
import json
import threading

from collections import OrderedDict

import humanize

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.http import JsonResponse

from gremlin_python.process.traversal import T

from cartographer.gizmo import Gizmo
from cartographer.gizmo.models import Resource, Workspace
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

    workspace_data = []
    workspace_vertices = Workspace.vertices.all()

    for w in workspace_vertices:
        try:
            terraform_version = w.get_current_state_revision().terraform_version
        except VertexDoesNotExistException:
            continue
        
        required_deps_count = w.get_dependency_count()
        redundant_deps_count = w.get_dependency_count(redundant=True)
        workspace_data.append({
            'name': w.name,
            'org_name': w.organization,
            'dependency_count': required_deps_count + redundant_deps_count,
            'r_dependency_count': redundant_deps_count,
            'terraform_version': terraform_version
        })

    context = {
        'stats': {
        },
        'workspace_data': workspace_data
    }

    return render(request, 'redundant-dependencies.html', context)