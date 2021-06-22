import os
import json
import threading

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
import networkx as nx

from gremlin_python.process.traversal import T

from cartographer.gizmo import Gizmo
from cartographer.gizmo.models import Workspace
from cartographer.models import TerraformCloudAPIKey, TerraformCloudOrganization


@login_required
def remotes_terraform_cloud(request):
    """View for managing Terraform Cloud data like Organizations and the API Keys
    that are required to interact with them.
    """
    context = {'stats': {}}

    organizations = TerraformCloudOrganization.objects.all()
    api_key_count = TerraformCloudAPIKey.objects.count()

    context['stats']['organizations_count'] = len(organizations)
    context['stats']['states_count'] = Workspace.vertices.count()
    context['stats']['api_keys_count'] = api_key_count
    context['organizations'] = [{
        'name': org.name,
        'total_workspaces': Workspace.vertices.count(organization=org.name),
        'refreshing': org.refreshing
    } for org in organizations]

    return render(request, 'admin-remotes-tfcloud.html', context)
