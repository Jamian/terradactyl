from django.contrib.auth.decorators import login_required
from django.urls import path

from .views import auth, remotes, states as states_view, reports as reports_view
from .apis import terraform_cloud, states as states_api, insights as insights_api


urlpatterns = [
    # Views
    path('', states_view.index, name='index'),
    path('login', auth.LoginView.as_view(), name='login'),
    path('logout', auth.LogoutView.as_view(), name='logout'),
    path('states', states_view.states, name='states'),
    path('states/<state_name>', states_view.state, name='states'),
    path('organizations', remotes.organizations, name='organizations'),
    path('organizations/<organization_name>', remotes.organization, name='organization'),
    path('reports/terraform-versions', reports_view.terraform_versions, name='reports-terraform-versions'),
    path('reports/redundant-dependencies', reports_view.redundant_dependencies, name='reports-redundant-dependencies'),

    # Apis
    path('api/v1/dt/states', states_api.get_table_states_data, name='dt-get-states'),
    path('api/v1/g/states', states_api.get_graph_states_data, name='g-get-states'),
    path('api/v1/g/states/<state_name>', states_api.get_state, name='get-state'),
    path('api/v1/g/states/<state_name>/resources', states_api.get_state_resources, name='get-state-resources'),
    path('api/v1/g/states/<state_name>/run-order', states_api.get_state_run_order, name='get-state-run-order'),
    path('api/v1/terraform-cloud/api-keys', login_required(terraform_cloud.TerraformCloudAPIKeys.as_view()), name='terraform-cloud-api-keys'),
    path('api/v1/terraform-cloud/organizations', login_required(terraform_cloud.TerraformCloudOrganizations.as_view()), name='terraform-cloud-organizations'),

    path('api/v1/insights/daily-change', insights_api.daily_change, name='insights'),
]
