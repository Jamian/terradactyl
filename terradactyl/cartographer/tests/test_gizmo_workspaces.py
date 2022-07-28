import datetime
import time

from django.test import TestCase

from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.graph_traversal import __
from gremlin_python.structure.graph import Graph


from cartographer.gizmo.models import State, Workspace
from cartographer.gizmo.models.exceptions import VertexDoesNotExistException

LUT_TERRAFORM_REMOTE_STATE = 'terraform_remote_state'
LUT_TFE_OUTPUTS = 'tfe_outputs'
WORKSPACE_LABEL = 'workspace'

class TestGizmoWorkspaces(TestCase):

    def setUp(self):
        self.g = Graph().traversal().withRemote(DriverRemoteConnection(f'ws://localhost:8182/gremlin', 'g'))
        self.g.V().drop().iterate()
    
    def tearDown(self):
        self.g.V().drop().iterate()
        return super().tearDown()

    def test_fetch_workspace_success(self):
        expected_id = '1234'
        expected_name = 'foo'
        expected_organization = 'happylittleorg'
        expected_created_at = time.time()
        expected_last_updated = time.time()
        self.g.addV(Workspace.label) \
            .property('workspace_id', expected_id) \
            .property('name', expected_name) \
            .property('organization', expected_organization) \
            .property('created_at', expected_created_at) \
            .property('last_updated', expected_last_updated).next()

        ws = Workspace.vertices.get(name=expected_name, organization=expected_organization)
        self.assertEqual(ws.workspace_id, expected_id)
        self.assertEqual(ws.name, expected_name)
        self.assertEqual(ws.organization, expected_organization)
        self.assertEqual(ws.created_at, expected_created_at)
        self.assertEqual(ws.last_updated, expected_last_updated)

    def test_fetch_missing_workspace_success(self):
        with self.assertRaises(VertexDoesNotExistException):
            Workspace.vertices.get(name='missing', organization='missing')

    def test_create_workspace_success(self):
        expected_id = '1234'
        expected_name = 'bob'
        expected_organization = 'happylittleorg'
        expected_created_at = time.time()

        Workspace.vertices.create(
            workspace_id=expected_id,
            name=expected_name,
            organization=expected_organization,
            created_at=expected_created_at
        )

        self.assertEqual(self.g.V().hasLabel(WORKSPACE_LABEL).count().next(), 1)
        Workspace.vertices.get(name=expected_name, organization=expected_organization)

    def test_create_workspace_get_or_create_creates(self):
        expected_id = '1234'
        expected_name = 'bob'
        expected_organization = 'happylittleorg'
        expected_created_at = time.time()

        Workspace.vertices.get_or_create(
            workspace_id=expected_id,
            name=expected_name,
            organization=expected_organization,
            created_at=expected_created_at
        )

        self.assertEqual(self.g.V().hasLabel(WORKSPACE_LABEL).count().next(), 1)
        ws = Workspace.vertices.get(name=expected_name, organization=expected_organization)
        self.assertEqual(ws.workspace_id, expected_id)
        self.assertEqual(ws.name, expected_name)
        self.assertEqual(ws.organization, expected_organization)
        self.assertEqual(ws.created_at, expected_created_at)

        last_updated_dt = datetime.datetime.fromtimestamp(float(ws.last_updated))
        ten_seconds_ago = datetime.timedelta(seconds=10)
        now = datetime.datetime.now()
        self.assertTrue(True if ((now - last_updated_dt) < ten_seconds_ago) else False)

    def test_create_workspace_get_or_create_gets(self):
        expected_id = '1234'
        expected_name = 'bob'
        expected_organization = 'happylittleorg'
        expected_created_at = time.time()
        expected_last_updated = (datetime.datetime.now() - datetime.timedelta(seconds=30)).timestamp()

        self.g.addV(Workspace.label) \
            .property('workspace_id', expected_id) \
            .property('name', expected_name) \
            .property('organization', expected_organization) \
            .property('created_at', expected_created_at) \
            .property('last_updated', expected_last_updated).next()

        self.assertEqual(self.g.V().hasLabel(WORKSPACE_LABEL).count().next(), 1)

        ws = Workspace.vertices.get_or_create(
            workspace_id=expected_id,
            name=expected_name,
            organization=expected_organization,
            created_at=expected_created_at
        )
        self.assertEqual(ws.workspace_id, expected_id)
        self.assertEqual(ws.name, expected_name)
        self.assertEqual(ws.organization, expected_organization)
        self.assertEqual(ws.created_at, expected_created_at)

        last_updated_dt = datetime.datetime.fromtimestamp(float(ws.last_updated))
        ten_seconds_ago = datetime.timedelta(seconds=10)
        now = datetime.datetime.now()
        self.assertTrue(True if ((now - last_updated_dt) > ten_seconds_ago) else False)

    def test_create_workspace_terraform_remote_state_dependency(self):
        expected_id_1 = '0'
        expected_name_1 = 'bob'
        expected_organization_1 = 'happylittleorg'
        expected_created_at_1 = time.time()

        expected_id_2 = '1'
        expected_name_2 = 'steve'
        expected_organization_2 = 'happylittleorg'
        expected_created_at_2 = time.time()

        ws_1 = Workspace.vertices.create(
            workspace_id=expected_id_1,
            name=expected_name_1,
            organization=expected_organization_1,
            created_at=expected_created_at_1
        )
        
        ws_2 = Workspace.vertices.create(
            workspace_id=expected_id_2,
            name=expected_name_2,
            organization=expected_organization_2,
            created_at=expected_created_at_2
        )
        
        ws_1.depends_on(ws_2, lookup_type=LUT_TERRAFORM_REMOTE_STATE)

        self.assertEqual(self.g.E().count().next(), 1)
        self.assertEqual(self.g.E().has('type', 'tfe_outputs').count().next(), 0)

        self.assertEqual(self.g.V().hasLabel(WORKSPACE_LABEL).outE('depends_on').count().next(), 1)
        self.assertEqual(self.g.V().hasLabel(WORKSPACE_LABEL).inE('depends_on').count().next(), 1)

        self.assertEqual(self.g.V().hasLabel(WORKSPACE_LABEL).has('name', expected_name_1).outE('depends_on').count().next(), 1)
        self.assertEqual(self.g.V().hasLabel(WORKSPACE_LABEL).has('name', expected_name_2).outE('depends_on').count().next(), 0)

    def test_create_get_workspace_dependencies(self):
        expected_id_1 = '0'
        expected_name_1 = 'bob'
        expected_organization_1 = 'happylittleorg'
        expected_created_at_1 = time.time()

        expected_dependencies = [
            {
                'name': 'steve',
                'organization': 'happylittleorg',
                'created_at': time.time(),
                'redundant': False,
                'type': LUT_TERRAFORM_REMOTE_STATE
            }, {
                'name': 'foo',
                'organization': 'happylittleorg',
                'created_at': time.time(),
                'redundant': True,
                'type': LUT_TFE_OUTPUTS
            }, {
                'name': 'gary',
                'organization': 'happylittleorg',
                'created_at': time.time(),
                'redundant': False,
                'type': LUT_TFE_OUTPUTS
            }
        ]

        ws_1 = Workspace.vertices.create(
            workspace_id=expected_id_1,
            name=expected_name_1,
            organization=expected_organization_1,
            created_at=expected_created_at_1
        )

        for i, dep in enumerate(expected_dependencies):
            dep_ws = Workspace.vertices.create(
                workspace_id=str(i + 1),
                name=dep['name'],
                organization=dep['organization'],
                created_at=dep['created_at']
            )
            ws_1.depends_on(dep_ws, lookup_type=dep['type'], redundant=dep['redundant'])

        dependencies = ws_1.get_dependencies()
        self.assertEqual(len(dependencies), len(expected_dependencies))
        
        redundant_dependencies = ws_1.get_dependencies(redundant=True)
        self.assertEqual(len(redundant_dependencies), 1)

        non_redundant_dependencies = ws_1.get_dependencies(redundant=False)
        self.assertEqual(len(non_redundant_dependencies), 2)

        tfe_outputs = ws_1.get_dependencies(lookup_type=LUT_TFE_OUTPUTS)
        self.assertEqual(len(tfe_outputs), 2)

        remote_state = ws_1.get_dependencies(lookup_type=LUT_TERRAFORM_REMOTE_STATE)
        self.assertEqual(len(remote_state), 1)

        redundant_tfe_outputs = ws_1.get_dependencies(lookup_type=LUT_TFE_OUTPUTS, redundant=True)
        self.assertEqual(len(redundant_tfe_outputs), 1)

        non_redundant_remote_states = ws_1.get_dependencies(lookup_type=LUT_TERRAFORM_REMOTE_STATE, redundant=False)
        self.assertEqual(len(non_redundant_remote_states), 1)

    def test_create_get_dependency_count(self):
        expected_id_1 = '0'
        expected_name_1 = 'bob'
        expected_organization_1 = 'happylittleorg'
        expected_created_at_1 = time.time()

        expected_dependencies = [
            {
                'name': 'steve',
                'organization': 'happylittleorg',
                'created_at': time.time(),
                'redundant': False
            }, {
                'name': 'foo',
                'organization': 'happylittleorg',
                'created_at': time.time(),
                'redundant': True
            }, {
                'name': 'gary',
                'organization': 'happylittleorg',
                'created_at': time.time(),
                'redundant': True
            },
        ]

        ws_1 = Workspace.vertices.create(
            workspace_id=expected_id_1,
            name=expected_name_1,
            organization=expected_organization_1,
            created_at=expected_created_at_1
        )

        for i, dep in enumerate(expected_dependencies):
            dep_ws = Workspace.vertices.create(
                workspace_id=str(i + 1),
                name=dep['name'],
                organization=dep['organization'],
                created_at=dep['created_at']
            )
            ws_1.depends_on(dep_ws, lookup_type=LUT_TFE_OUTPUTS, redundant=dep['redundant'])

        total_count = ws_1.get_dependency_count()
        self.assertEqual(total_count, len(expected_dependencies))

        expected_redundant_count = 0
        expected_not_redundant_count = 0
        
        for d in expected_dependencies:
            if d['redundant']:
                expected_redundant_count += 1
            else:
                expected_not_redundant_count += 1

        redundant_count = ws_1.get_dependency_count(redundant=True)
        not_redundant_count = ws_1.get_dependency_count(redundant=False)

        self.assertEqual(redundant_count, expected_redundant_count)
        self.assertEqual(not_redundant_count, expected_not_redundant_count)
        
        with self.assertRaises(TypeError):
            ws_1.get_dependency_count(redundant='False')

    def test_create_get_workspace_chain(self):
        expected_id_1 = '0'
        expected_name_1 = 'bob'
        expected_organization_1 = 'happylittleorg'
        expected_created_at_1 = time.time()

        expected_dependencies = [
            {
                'name': 'steve',
                'organization': 'happylittleorg',
                'created_at': time.time(),
            }, {
                'name': 'foo',
                'organization': 'happylittleorg',
                'created_at': time.time(),
            }, {
                'name': 'gary',
                'organization': 'happylittleorg',
                'created_at': time.time(),
            },
        ]

        ws_1 = Workspace.vertices.create(
            workspace_id=expected_id_1,
            name=expected_name_1,
            organization=expected_organization_1,
            created_at=expected_created_at_1
        )

        prev_dep = ws_1
        for i, dep in enumerate(expected_dependencies):
            dep_ws = Workspace.vertices.create(
                workspace_id=str(i + 1),
                name=dep['name'],
                organization=dep['organization'],
                created_at=dep['created_at']
            )
            dep_ws.depends_on(prev_dep, lookup_type=LUT_TFE_OUTPUTS)
            prev_dep = dep_ws

        dependencies = ws_1.get_dependencies()
        self.assertEqual(len(dependencies), 0)

        dependencies = prev_dep.get_dependencies()
        self.assertEqual(len(dependencies), 1)

        chain = prev_dep.get_chain(vertices_only=True)
        self.assertEqual(len(chain), len(expected_dependencies))

        chain.reverse()
        for i, ws in enumerate(chain):
            if i == 0:
                self.assertEqual(ws.name, ws_1.name)
            else:
                self.assertEqual(ws.name, expected_dependencies[i - 1]['name'])

    def test_workspace_count_by_current_rev(self):
        expected_id = '1234'
        expected_name = 'foo'
        expected_organization = 'happylittleorg'
        expected_created_at = time.time()
        expected_last_updated = time.time()
        workspace_012 = self.g.addV(Workspace.label) \
            .property('workspace_id', expected_id) \
            .property('name', expected_name) \
            .property('organization', expected_organization) \
            .property('created_at', expected_created_at) \
            .property('last_updated', expected_last_updated).next()

        state_012 = self.g.addV(State.label) \
                .property('state_id', '1') \
                .property('resource_count', '123') \
                .property('serial', '12') \
                .property('terraform_version', '0.12.3') \
                .property('created_at', expected_created_at).next()

        self.g.V(workspace_012).as_('v') \
            .V(state_012).as_('t') \
            .coalesce(
            __.inE('has_current_state').where(__.outV().as_('v')),
            __.addE('has_current_state').from_('v')
        ).next()

        expected_12_count = 20
        for i in range(expected_12_count):
            workspace_12 = self.g.addV(Workspace.label) \
                .property('workspace_id', f'{expected_id}_{i}') \
                .property('name', f'{expected_name}_{i}') \
                .property('organization', expected_organization) \
                .property('created_at', expected_created_at) \
                .property('last_updated', expected_last_updated).next()

            state_12 = self.g.addV(State.label) \
                    .property('state_id', '1') \
                    .property('resource_count', '123') \
                    .property('serial', '12') \
                    .property('terraform_version', '1.2.0') \
                    .property('created_at', expected_created_at).next()

            self.g.V(workspace_12).as_('v') \
                .V(state_12).as_('t') \
                .coalesce(
                __.inE('has_current_state').where(__.outV().as_('v')),
                __.addE('has_current_state').from_('v')
            ).next()

        expected_013_count = 42
        for i in range(expected_013_count):
            workspace_013 = self.g.addV(Workspace.label) \
                .property('workspace_id', f'{expected_id}_{i}') \
                .property('name', f'{expected_name}_{i}') \
                .property('organization', expected_organization) \
                .property('created_at', expected_created_at) \
                .property('last_updated', expected_last_updated).next()

            state_013 = self.g.addV(State.label) \
                    .property('state_id', '1') \
                    .property('resource_count', '123') \
                    .property('serial', '12') \
                    .property('terraform_version', '0.13.0') \
                    .property('created_at', expected_created_at).next()

            self.g.V(workspace_013).as_('v') \
                .V(state_013).as_('t') \
                .coalesce(
                __.inE('has_current_state').where(__.outV().as_('v')),
                __.addE('has_current_state').from_('v')
            ).next()

        group_counts = Workspace.vertices.count_by_current_rev('terraform_version')
        self.assertEqual(group_counts['0.12.3'], 1)
        self.assertEqual(group_counts['0.13.0'], expected_013_count)
        self.assertEqual(group_counts['1.2.0'], expected_12_count)