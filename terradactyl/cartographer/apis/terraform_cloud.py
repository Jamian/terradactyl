import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from cartographer.models import TerraformCloudAPIKey, TerraformCloudOrganization
from cartographer.tasks.terraform_cloud import sync_organization


BASE_URL = 'https://app.terraform.io'

logger = logging.getLogger(__name__)


def _get_terraform_cloud_api_keys(request):
    """Fetch all stored Terraform Cloud API Keys and return them.
    """
    data = {}
    api_keys = TerraformCloudAPIKey.objects.all()
    data['api-keys'] = [key.name for key in api_keys]

    return JsonResponse(data)


def _create_terraform_cloud_api_key(request):
    """Store a new Terraform Cloud API key.
    """
    request_json = json.loads(request.body)
    # TODO : Handle bad input

    api_key_name = request_json['api-key']['name']
    api_key_value = request_json['api-key']['value']

    TerraformCloudAPIKey.objects.create(name=api_key_name, value=api_key_value)

    return HttpResponse(status=201)


@require_http_methods(['GET', 'PUT'])
def terraform_cloud_api_keys(request):
    """Wrapper function for handling Terraform Cloud API Key requests.
    """

    if request.method == 'GET':
        return _get_terraform_cloud_api_keys(request)
    elif request.method == 'PUT':
        return _create_terraform_cloud_api_key(request)


def _get_terraform_cloud_organizations(request):
    # TODO : This should be synch org. Or Refresh/Sync = true?
    org_names = request.GET.get('organizations', None)
    if org_names:
        org_names = org_names.split(',')

    # Sync Organization
      # Get a list of Workspaces
        # For each workspace, create the node (group 1)
        # task.delay : pull state and update node with info / dependencies (can't complete until group 1 is done)
    for org_name in org_names:
        sync_organization.delay(org_name)

    return HttpResponse(status=200)


def _put_terraform_cloud_organization(request):
    request_json = json.loads(request.body)

    api_key = TerraformCloudAPIKey.objects.get(
        name=request_json['organization']['key'])
    TerraformCloudOrganization.objects.create(
        name=request_json['organization']['name'], api_key=api_key)

    return HttpResponse(status=201)


@require_http_methods(['GET', 'PUT'])
def terraform_cloud_organizations(request):
    """Wrapper function for handling Terraform Cloud Organisation requests.
    """

    if request.method == 'GET':
        return _get_terraform_cloud_organizations(request)
    elif request.method == 'PUT':
        return _put_terraform_cloud_organization(request)
