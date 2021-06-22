from django.urls import path

from .views import auth, remotes, states as states_view
from .apis import terraform_cloud, states as states_api

urlpatterns = [
    # Views
    path('', states_view.index, name='index'),
    path('login', auth.login, name='login'),
    path('logout', auth.logout, name='logout'),
    path('states', states_view.states, name='states'),
    path('states/<state_name>', states_view.state, name='states'),
    path('admin/remotes/terraform-cloud', remotes.remotes_terraform_cloud, name='remotes-terraform-cloud'),

    # Apis
    path('api/v1/states', states_api.get_states, name='get-states'),
    path('api/v1/states/<state_name>', states_api.get_state, name='get-state'),
    path('api/v1/states/<state_name>/resources', states_api.get_state_resources, name='get-state-resources'),
    path('api/v1/states/<state_name>/run-order', states_api.get_state_run_order, name='get-state-run-order'),
    path('api/v1/terraform-cloud/api-keys', terraform_cloud.terraform_cloud_api_keys, name='terraform-cloud-api-keys'),
    path('api/v1/terraform-cloud/organizations', terraform_cloud.terraform_cloud_organizations, name='terraform-cloud-organizations'),
]
