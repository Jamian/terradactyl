import humanize

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Q
from django.views.decorators.http import require_http_methods


from cartographer.gizmo.models import Workspace
from cartographer.models import OrganizationSyncJob, TerraformCloudOrganization


@login_required
@require_http_methods(['GET'])
def organizations(request):
    """View for managing Terraform Cloud data like Organizations and the API Keys
    that are required to interact with them.
    """
    context = {'stats': {}}

    organizations = TerraformCloudOrganization.objects.all()
    # api_key_count = TerraformCloudAPIKey.objects.count()

    context['stats']['organizations_count'] = len(organizations)
    context['organizations'] = []

    for org in organizations:
        sync_job = org.organizationsyncjob_set.filter(~Q(state=OrganizationSyncJob.COMPLETE))
        if sync_job:
            state = sync_job[0].state
            duration = sync_job[0].duration
        else:
            try:
                sync_job = org.organizationsyncjob_set.latest('finished_at')
                state = sync_job.state
                duration = sync_job.duration
            except:
                state = None
                duration = None
                
        context['organizations'].append({
            'name': org.name,
            'total_workspaces': Workspace.vertices.count(organization=org.name),
            'refreshing': org.refreshing,
            'refresh_state': state,
            'refresh_duration': humanize.naturaldelta(duration)
        })

    return render(request, 'organizations.html', context)

@login_required
@require_http_methods(['GET'])
def organization(request, organization_name):
    """View for managing Terraform Cloud data like Organizations and the API Keys
    that are required to interact with them.
    """
    context = {'stats': {
        'workspaces_count': Workspace.vertices.count(organization=organization_name)}, 'organzation_name': organization_name}

    organization = TerraformCloudOrganization.objects.get(name=organization_name)

    return render(request, 'organization.html', context)
