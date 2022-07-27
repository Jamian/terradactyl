import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views import View

from cartographer.models import TerraformCloudAPIKey, TerraformCloudOrganization
from cartographer.tasks.terraform_cloud import sync_organization


logger = logging.getLogger(__name__)


class TerraformCloudAPIKeys(View):
    def get(self, request):
        data = {}
        api_keys = TerraformCloudAPIKey.objects.all()
        data['api-keys'] = [key.name for key in api_keys]
        return JsonResponse(data)

    def put(self, request):
        request_json = json.loads(request.body)
        # TODO : Handle bad input

        api_key_name = request_json['api-key']['name']
        api_key_value = request_json['api-key']['value']

        TerraformCloudAPIKey.objects.create(name=api_key_name, value=api_key_value)

        return HttpResponse(status=201)

class TerraformCloudOrganizations(View):
    def get(self, request):
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

    def put(self, request):
        request_json = json.loads(request.body)

        api_key = TerraformCloudAPIKey.objects.get(
            name=request_json['organization']['key'])
        TerraformCloudOrganization.objects.create(
            name=request_json['organization']['name'], api_key=api_key)

        return HttpResponse(status=201)
