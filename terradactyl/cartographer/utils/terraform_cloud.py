import datetime
import logging
import threading

import requests

from cartographer.models import TerraformCloudOrganization

logger = logging.getLogger(__name__)

PAGE_SIZE = 100 # TODO : Get from settings?

class WorkspaceNotFoundException(Exception):
    """Raised when an attempt to fetch Workspace info from Terraform Cloud
    results in a returned 404 and 'not found' message.
    """
    pass


def parse_tf_datetime_str(datetime_str):
    """Parse Terraform Cloud time string into a datetime object.
    Example Terraform Cloud format: 2019-12-12T08:38:11.690Z

    Args
        datetime_str: the datetime string to convert into a datetime object.
    
    Returns
        datetime object for the given string time.
    """
    return datetime.datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S.%fZ')


class TerraformCloudClient():
    """Client containing functionality for interacting with the Terraform Cloud
    APIs and returning smaller, prepared datasets that the calling functions will
    find more easier to interact with.
    """
    base_url = 'https://app.terraform.io'

    def __init__(self, api_key):
        self._api_key = api_key
        self._headers = {
            'Authorization': 'Bearer ' + api_key,
            'Content-Type': 'application/vnd.api+jso'
        }

    def _get_workspaces_page(self, organization_name, page_number, workspaces):
        """Follow a paginated link based on given page_number and parse the Workspace information.

        Args
            organization_name: the name of the Terraform Cloud Organiziation to fetch the workspaces for.
            page_number: the pagination page number that this function call will fetch (as it usually runs threaded).
            workspaces: the dict to update with the fetched workspaces.
        """
        pagination_url = f'https://app.terraform.io/api/v2/organizations/{organization_name}/workspaces?page%5Bnumber%5D={page_number}&page%5Bsize%5D={PAGE_SIZE}'
        workspaces_response = requests.get(pagination_url, headers=self._headers)
        response_json = workspaces_response.json()
        try:
            for workspace_json in response_json['data']:
                try:
                    workspace = {}
                    workspace['id'] = workspace_json['id']
                    workspace['name'] = workspace_json['attributes']['name']
                    workspace['organization'] = organization_name
                    workspace['created_at'] = parse_tf_datetime_str(workspace_json['attributes']['created-at']).timestamp()
                    workspaces.append(workspace)
                except Exception as error:
                    workspace_name = workspace['name']
                    logger.warning(f'An error occurred fetching workspace {workspace_name}. Error: {error}.')
                    continue
        except Exception as error:
            logger.warning(f'An error occurred fetching workspaces for Organization: {organization_name}. Error: {error}.')


    def get_current_state_and_resources(self, state_lookup_path):
        """Fetches the current state and returns information about it along with
        a list of it's resources, parsed straight out of the state file for further parsing.
        
        Args
            state_lookup_path: the Terraform Cloud API path to fetch the current state version.
        Returns
            current_state: dict of current_state that contains parsed metadata about the state, for example:
                {
                    'state_id': 'SomeRandomStateId',
                    'serial': 123,
                    'resource_count': 54,
                    'created_at': 1231414124124,
                    'terraform_version': '0.14.11'
                }
            state_resources: list of resources lifted straight from the state file
        """
        state_lookup_url = self.base_url + state_lookup_path
        state_response = requests.get(state_lookup_url, headers=self._headers)
        state_response_json = state_response.json()

        hosted_state_dl_url = state_response_json['data']['attributes']['hosted-state-download-url']

        state_response = requests.get(hosted_state_dl_url, self._headers)
        state = state_response.json()

        current_state = {}
        current_state['state_id'] = state_response_json['data']['id']
        current_state['serial'] = state['serial']
        current_state['resource_count'] = 0
        current_state['created_at'] = parse_tf_datetime_str(state_response_json['data']['attributes']['created-at']).timestamp()
        current_state['terraform_version'] = state['terraform_version']

        for resource in state['resources']:
            current_state['resource_count'] += len(resource['instances'])

        return current_state, state['resources']


    def chain(self, workspace_name: str, organization_name: str):
        """Fetch the full chain of Workspaces directly or indirectly related to the given workspace.

        Args
            workspace_name: the name of the Terraform Cloud Workspace to fetch details about.
            organization_name: the name of the Terraform Cloud organization that the Workspace belongs to.

        Returns
            chain_data: a dictionary containing all Workspaces indirectly or directly related. For example:
            {
                'TFCloudWorkdSpaceId': {
                    'id': 'TFCloudWorkdSpaceId',
                    'organization_name': 'SomeOrganizationName',
                    'name': 'SomeName-For-Your-Workspace',
                    'created_at': '2018-03-08T22:30:00.404Z',
                    'current_state': {'state_id': 'a_state_id', 'serial': 123, 'resource_count': 4, 'created_at': 'atimestamp', 'terraform_version': '0.14.11'},
                    'depends_on': {'data.terraform_remote_state.more_namespace': { 'workspace_name': 'HappyLittleWorkspace', 'organization': 'Org1', 'redundant': True}}
                }
            }
        """
        already_fetched = []
        deps_to_fetch = []
        workspace_data = self.workspace(workspace_name=workspace_name, organization_name=organization_name)
        chain_data = {
            workspace_data['id']: workspace_data
        }

        workspace_name = workspace_data['name']
        workspace_org = organization_name
        already_fetched.append(f'{workspace_name}:{workspace_org}')
        for _, dep_info in workspace_data['depends_on'].items():
            deps_to_fetch.append({'workspace_name': dep_info['workspace_name'], 'organization': dep_info['organization']})
        
        for dep_info in deps_to_fetch:
            workspace_name = dep_info['workspace_name']
            workspace_org = dep_info['organization']
            if f'{workspace_name}:{workspace_org}' not in already_fetched:
                workspace_data = self.workspace(workspace_name=workspace_name, organization_name=organization_name)
                chain_data[workspace_data['id']] = workspace_data
                already_fetched.append(f'{workspace_name}:{workspace_org}')
                for _, new_dep_info in workspace_data['depends_on'].items():
                    deps_to_fetch.append({'workspace_name': new_dep_info['workspace_name'], 'organization': new_dep_info['organization']})
                
                deps_to_fetch.append({'workspace_name': dep_info['workspace_name'], 'organization': dep_info['organization']})

        return chain_data

    def workspace(self, workspace_name: str, organization_name: str):
        """Fetch a single workspace and return a dict containing useful information about it

        Args
            workspace_name: the name of the Terraform Cloud Workspace to fetch details about.
            organization_name: the name of the Terraform Cloud organization that the Workspace belongs to.

        Returns
            workspace_dict: dictionary containing information about the Workspace, for example:
            {
                'id': 'TFCloudWorkdSpaceId',
                'organization_name': 'SomeOrgName',
                'name': 'SomeName-For-Your-Workspace',
                'created_at': '12414123124124124',
                'current_state': {'state_id': 'a_state_id', 'serial': 123, 'resource_count': 4, 'created_at': '112313123123123', 'terraform_version': '0.14.11'},
                'depends_on': {'data.terraform_remote_state.more_namespace': { 'workspace_name': 'HappyLittleWorkspace', 'organization': 'Org1', 'redundant': True}}
            }
        """

        workspace_dict = {}
        workspace_request_response = requests.get(self.base_url + f'/api/v2/organizations/{organization_name}/workspaces/{workspace_name}', headers=self._headers)

        response_json = workspace_request_response.json()

        if 'errors' in response_json:
            for error in response_json['errors']:
                if error['status'] == '404' and error['title'] == 'not found':
                    raise WorkspaceNotFoundException

        try:
            workspace_dict['id'] = response_json['data']['id']
        except KeyError as e:
            logger.error('KeyError when looking up data in Workspace response.')
            logger.debug(response_json)
            logger.debug(workspace_request_response.status_code)

        workspace_dict['name'] = response_json['data']['attributes']['name']
        workspace_dict['organization_name'] = organization_name
        workspace_dict['created_at'] = parse_tf_datetime_str(response_json['data']['attributes']['created-at'])

        try:
            state_lookup_path = response_json['data']['relationships']['current-state-version']['links']['related']
            current_state, state_resources = self.get_current_state_and_resources(state_lookup_path)
            workspace_dict['depends_on'] = {}
            workspace_dict['current_state'] = current_state

            # TODO : Refactor this into a function as well
            data_resources = [r for r in state_resources if (r['mode'] == 'data' and r['type'] == 'terraform_remote_state')]
            for dr in [dr for dr in data_resources if len(dr['instances']) > 0]:
                # TODO : Is the hard coded 0 good enough? Not sure of multiple instances use cases.
                namespace = build_namespace(dr)

                workspace_name = dr['instances'][0]['attributes']['config']['value']['workspaces']['name']
                if namespace not in workspace_dict['depends_on']:
                    redundant = False if 'module' in dr else True
                    workspace_dict['depends_on'][namespace] = {
                        'workspace_name': workspace_name,
                        'organization': dr['instances'][0]['attributes']['config']['value']['organization'],
                        'redundant': redundant
                        # TODO : Modules have remote_states that are required but not used. So although redundant they are required.
                    }
            managed_resources = [r for r in state_resources if r['mode'] == 'managed']
            for r in [r for r in managed_resources if len(r['instances']) > 0]:
                instance = r['instances'][0]   # TODO : Is this sufficient, do all instances all share the same dependencies?
                if 'dependencies' in instance:
                    for dependency in [d for d in instance['dependencies'] if 'terraform_remote_state' in d]:
                        if dependency not in workspace_dict['depends_on']:
                            # raise Exception(f'Error parsing dependencies... missing terraform_remote_state referenced. Dependency: {dependency}. Workspace: {workspace_dict["name"]}')
                            # Seems like an optional data in a module is classed as a dep, even though it is not used... so just log info this for now?
                            logger.debug(f'Error parsing dependencies... missing terraform_remote_state referenced. Dependency: {dependency}. Workspace: {workspace_dict["name"]}')
                        else:
                            workspace_dict['depends_on'][dependency]['redundant'] = False
                            # TODO : Modules have remote_states that are required but not used. So although redundant they are required.
        except KeyError:
            logger.debug('Skipped empty Workspace.')
            
        return workspace_dict

    def workspaces(self, organization_name: str):
        """Fetch all workspaces for an organization, parse them and return a dict with the key as workspace
        name, dict contains only useful pieces of information/data that can be used by the calling function.
        Spawns x number of threads to fetch and parse responses concurrently.

        Args:
            organization_name: The name of the Terraform Cloud Organization to fetch Workspaces for.

        Returns:
            A dict of data parsed from the Terraform Cloud response. For example:
            
            {
                'someworkspace_id': {
                    'name': 'SomeworkSpaceName'
                    'current_state': {'state_id': 'a_state_id', 'serial': 123, 'resource_count': 4, 'created_at': 'atimestamp', 'terraform_version': '0.14.4'},
                    'depends_on': 'anotherWorkspace_id'
                }
            }

        """
        workspaces = []
        initial_request_response = requests.get(self.base_url + f'/api/v2/organizations/{organization_name}/workspaces?page%5Bsize%5D={PAGE_SIZE}', headers=self._headers)
        response_json = initial_request_response.json()

        if 'meta' not in response_json:
            total_pages = 1
        else:
            total_pages = response_json['meta']['pagination']['total-pages']

        logger.info(f'Fetching {total_pages} pages worth of Workspaces for Organization {organization_name}')
        for page_number in range(1, total_pages + 1):
            self._get_workspaces_page(organization_name, page_number, workspaces)

        logger.info(f'Parsed {len(workspaces)} workspaces.')
        return workspaces

    def resources(self, organization_name, workspace_name):
        resources = {
            'resources': {}
        }
        response = requests.get(self.base_url + f'/api/v2/organizations/{organization_name}/workspaces/{workspace_name}', headers=self._headers)
        workspace_json = response.json()
        state_lookup_path = workspace_json['data']['relationships']['current-state-version']['links']['related']

        _, state_resources = self.get_current_state_and_resources(state_lookup_path)

        known_data_deps = []   # Store a list of data dependencies as they're seen so that we can check for redundant cross state dependencies.

        for resource in state_resources:
            namespace = build_namespace(resource)
            resource_info = {
                'name': resource['name'],
                'resource_type': resource['type'],
                'namespace': namespace,
                'mode': resource['mode'],
                'instances': [],
                'depends_on': []
            }
            for instance in [ i for i in resource['instances'] if (resource['mode'] != 'data' and resource['type'] != 'terraform_remote_state')]:
                if 'index_key' not in instance:
                    # If a resource doesn't have instances (is singular anyway) then there is no key.
                    # To make our life easier we'll just default these to _default.
                    # TODO : This is probably misleading, should maybe remove this?
                    # Do we still need this or just go TF 1+ support only?
                    index_key = '_default'
                else:
                    index_key = instance['index_key']
                resource_info['instances'].append({
                    'index_key': index_key,
                    'iid': instance['attributes']['id']
                })
                if 'dependencies' in instance:
                    for dependency in instance['dependencies']:
                        # For now let's just show deps for the parent resource, rather than each instance.
                        # It looks like all instances of the same resource share the same dependencies anyway?
                        if dependency not in resource_info['depends_on']:
                            resource_info['depends_on'].append(dependency)
                        if dependency not in known_data_deps:
                            known_data_deps.append(dependency)

            resources['resources'][namespace] = resource_info
        return resources

    def state_revisions(self, workspace_name: str, organization_name: str, current_state_revision_id: str = None, initial_run=False):
        """For the given workspace_id fetch all state revisions. Will only fetch revisions that aren't already
        known about.

        TODO : This should only sync revisions that are new. No point going over them again.

        Args
            workspace_name: the name of the Terraform Cloud Workspace to fetch revisions for.
            organizaion_name: the name of the Terraform Cloud Organization to which the Workspace belongs.
            current_state_revision_id: the state Id for the most recent revision. Used to determine if anything needs to be done.
            initial_run: when set to True revisions are all imported, the current revision check is skipped.
        Returns
            A list of parsed state revisions information dicts in order from oldest to most recent.
            For example:
                [
                    {
                        'state_id': 'aknfaofnaowf',
                        'serial': 2,
                        ...
                        'terraform_version': '0.14.1'
                    },
                    {
                        'state_id': 'mpaoMDAOKNDOA',
                        'serial': 1,
                        ...
                        'terraform_version': '0.13.6'
                    }
                ]
        """

        params = {
            'filter[workspace][name]': workspace_name,
            'filter[organization][name]': organization_name
        }

        response = requests.get(self.base_url + f'/api/v2/state-versions', headers=self._headers, params=params)
        states_versions_response = response.json()

        states = []
        total_pages = 1
        state_ids_added = []
        if response.status_code == 200:
            if len(states_versions_response['data']) == 0:
                logger.info(f'No additional state revisions for {workspace_name}. Skipping.')
                return []
            
            if not initial_run:
                if (current_state_revision_id == states_versions_response['data'][0]['id']):
                # Assumes that they are always ordered? TODO : Does this account for weird state manipulations on the remote?
                    return []

            logger.debug(f'Fetching revisions for {workspace_name}, as local states are not up to date.')
            if 'meta' in states_versions_response:
                if 'pagination' in states_versions_response['meta']:
                    total_pages = states_versions_response['meta']['pagination']['total-pages']
            for state_version_info in states_versions_response['data']:
                # Fetch the state for parsing
                state_contents_response = requests.get(state_version_info['attributes']['hosted-state-download-url'])
                state_contents = state_contents_response.json()

                state_info = {
                    'state_id': state_version_info['id'],
                    'serial': state_version_info['attributes']['serial'],
                    'created_at': parse_tf_datetime_str(state_version_info['attributes']['created-at']).timestamp(),
                    'resource_count': len(state_contents['resources']),
                    'terraform_version': state_contents['terraform_version']
                }

                if state_version_info['id'] not in state_ids_added:
                    states.append(state_info)
                    state_ids_added.append(state_version_info['id'])
        else:
            logger.info(f'Non 200 response fetching revisions for workspace {workspace_name}.')
        
        # Handle Pagination
        for page_number in range(1, total_pages + 1):
            logger.info(f'Fetching {page_number} page for workspace {workspace_name} revisions.')
            # TODO : Optimise this so that (1) not sequential, thread it but careful of parent id linking
            #        and (2) only runs if it needs to (if this is a refresh we shouldnt need all pages,
            #        only until we reach what we already have).
            params = {
                'filter[workspace][name]': workspace_name,
                'filter[organization][name]': organization_name,
                'page[number]': page_number
            }
            response = requests.get(self.base_url + f'/api/v2/state-versions', headers=self._headers, params=params)
            pagination_state_response = response.json()
            if response.status_code == 200:
                for state_version_info in pagination_state_response['data']:
                    # Fetch the state for parsing
                    state_contents_response = requests.get(state_version_info['attributes']['hosted-state-download-url'])
                    state_contents = state_contents_response.json()

                    state_info = {
                        'state_id': state_version_info['id'],
                        'serial': state_version_info['attributes']['serial'],
                        'created_at': parse_tf_datetime_str(state_version_info['attributes']['created-at']).timestamp(),
                        'resource_count': len(state_contents['resources']),
                        'terraform_version': state_contents['terraform_version'],
                    }

                    if state_version_info['id'] not in state_ids_added:
                        states.append(state_info)
                        state_ids_added.append(state_version_info['id'])
                    else:
                        logger.info(f'Stopping revision fetch for {workspace_name}. Found all new revisions. Local is now up to date.')
            else:
                logger.info(f'Non 200 response {response.status_code} fetching revisions for workspace revision pagination {workspace_name}.')
        
        logger.info(f'Fetched {total_pages} pages for workspace {workspace_name} revisions.')

        return sorted(states, key=lambda k: k['serial'])


def build_namespace(resource: dict):
    """Given a resource dictionary, returns a full Terraform namespace for the resource.

    Args:
        resource (dict): the resource dictionary parsed from the remote state file

    Returns:
        A string respresenting the full Terraform namespace.
        For example: module.example_lambda.data.aws_iam_policy_document.lambda_function_trust_policy
    """
    name = resource['name']
    resource_type = resource['type']
    is_data = True if resource['mode'] == 'data' else False
    module = ''
    if 'module' in resource:
        module = resource['module']
        if '[' in module and resource['mode'] == 'data':
            # Remove these references to specific resources if data (and maybe others, have not seen that yet).
            temp_module = module.split('[')[0]
            module = temp_module + module.split(']')[1]

    namespace = '{module}{data}{resource_type}.{name}'

    data_str = 'data.' if is_data else ''
    module_str = f'{module}.' if module else ''
    namespace = namespace.format(module=module_str, data=data_str, resource_type=resource_type, name=name)

    return namespace
