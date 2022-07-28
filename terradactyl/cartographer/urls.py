from django.contrib.auth.decorators import login_required
from django.urls import path

from .views import auth, remotes, reports as reports_view, workspaces as workspaces_view
from .apis import terraform_cloud, workspaces as workspaces_api, insights as insights_api


urlpatterns = [
    # Views
    path('', workspaces_view.index, name='index'),
    path('login', auth.LoginView.as_view(), name='login'),
    path('logout', auth.LogoutView.as_view(), name='logout'),
    path('workspaces', workspaces_view.workspaces, name='workspaces'),
    path('workspaces/network', workspaces_view.workspaces_network, name='workspaces-network'),
    path('workspaces/<workspace_name>', workspaces_view.workspace, name='workspace'),
    path('organizations', remotes.organizations, name='organizations'),
    path('organizations/<organization_name>', remotes.organization, name='organization'),
    path('reports/terraform-versions', reports_view.terraform_versions, name='reports-terraform-versions'),
    path('reports/redundant-dependencies', reports_view.redundant_dependencies, name='reports-redundant-dependencies'),

    # Apis
    path('api/v1/dt/workspaces', workspaces_api.get_table_workspaces_data, name='dt-get-workspaces'),
    path('api/v1/g/workspaces', workspaces_api.get_graph_workspaces_data, name='g-get-workspaces'),
    path('api/v1/g/workspaces/<workspace_name>', workspaces_api.get_workspace, name='get-workspace'),
    path('api/v1/g/workspaces/<workspace_name>/resources', workspaces_api.get_workspace_resources, name='get-workspace-resources'),
    path('api/v1/g/workspaces/<workspace_name>/run-order', workspaces_api.get_workspace_run_order, name='get-workspace-run-order'),
    path('api/v1/terraform-cloud/api-keys', login_required(terraform_cloud.TerraformCloudAPIKeys.as_view()), name='terraform-cloud-api-keys'),
    path('api/v1/terraform-cloud/organizations', login_required(terraform_cloud.TerraformCloudOrganizations.as_view()), name='terraform-cloud-organizations'),

    path('api/v1/insights/daily-change', insights_api.daily_change, name='insights'),
]
