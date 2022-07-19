import datetime
import logging

from gremlin_python.process.traversal import T, Cardinality
from gremlin_python.process.graph_traversal import __, outE

from cartographer.gizmo import Gizmo
from cartographer.gizmo.models import Vertex
from cartographer.gizmo.models.state import State
from cartographer.gizmo.models.resource import Resource
from cartographer.gizmo.models.exceptions import VertexDoesNotExistException


logger = logging.getLogger(__name__)


LABEL = 'workspace'

class Workspace(Vertex):
    """Represents a Workspace in the graph database.
    """
    label = LABEL
    class vertices(Vertex.vertices):
        label = LABEL
        @classmethod
        def create(cls, workspace_id: str, name: str, organization: str, created_at: str):
            """
            Create a new Workspace Vertex
            created_at : the timestamp from TerraformCloud for when the Workspace was created. *Not* when it was created in Terradactyl.
            """
            last_updated = str(datetime.datetime.utcnow().timestamp())
            v = Gizmo().g.addV(Workspace.label) \
                .property('workspace_id', workspace_id) \
                .property('name', name) \
                .property('organization', organization) \
                .property('created_at', created_at) \
                .property('last_updated', last_updated).next()
            return Workspace(
                _id=v.id,
                workspace_id=workspace_id,
                name=name,
                organization=organization,
                last_updated=last_updated,
                created_at=created_at)

        @classmethod
        def count_by_current_rev(cls, group_by):
            return Gizmo().g.V().hasLabel(Workspace.label).outE('has_current_state').inV().groupCount().by(group_by).next()

        @classmethod
        def get(cls, **kwargs):
            """Fetch a vertex where the given kwargs are has() filters that are dynamically concatenated to build
            out the Gremlin query. E.g. where kwargs equals : {'name', 'bar', 'age', '12'} the query becomes
            Gizmo().g.V().has('name', 'bar').has('age', '12')

            Args
                kwargs: any number of .has() filters to apply to the base query.
            Returns 
                A new Workspace object representing the Workspace Vertex in the database.
            """
            base_query = Gizmo().g.V()
            for k, v in kwargs.items():
                base_query = base_query.has(k, v)

            if not Workspace.vertices.exists(**kwargs):
                raise VertexDoesNotExistException
            else:
                element_map = base_query.elementMap().next()
                # TODO : Returned more than one error
                return Workspace(
                    _id=element_map[T.id],
                    name=element_map['name'],
                    workspace_id=element_map['workspace_id'],
                    organization=element_map['organization'],
                    created_at=element_map['created_at'],
                    last_updated=element_map['last_updated']
                )

        @classmethod
        def get_or_create(cls, workspace_id: str, name: str, organization: str, created_at: str):
            """Try to find and return a Workspace. If the Vertex does not exist, create it and then return the Workspace.
            Args
                workspace_id: the Terraform Cloud identifier for the Workspace to fetch.
                name: the name of Workspace to fetch.
                organization: the name of the Terraform Cloud organization to which the Workspace belongs.
                created_at: the time string for when the Workspace was created
            Returns
                A new Workspace object representing the Workspace Vertex in the database.
            """
            try:
                ws = Workspace.vertices.get(
                    name=name, organization=organization)
            except VertexDoesNotExistException:
                ws = Workspace.vertices.create(**kwargs)
            return ws

        @classmethod
        def update_or_create(cls, workspace_id: str, name: str, organization: str, created_at: str):
            """try to find and return a Workspace and update it. If the Workspace does not exist, create it.
            
            Args
                workspace_id: the Terraform Cloud identifier for the Workspace to fetch.
                name: the name of Workspace to fetch.
                organization: the name of the Terraform Cloud organization to which the Workspace belongs.
                created_at: the time string for when the Workspace was created
            Returns
                A new Workspace object representing the Workspace Vertex in the database.
            """
            try:
                ws = Workspace.vertices.get(
                    name=name, organization=organization)
                ws.created_at = created_at
                ws.workspace_id = workspace_id
                ws.save()
            except VertexDoesNotExistException:
                ws = Workspace.vertices.create(
                    workspace_id=workspace_id,
                    name=name,
                    organization=organization,
                    created_at=created_at,
                )
            return ws

        @classmethod
        def filter(cls, name=None, organization=None):
            workspaces = []
            lookup_filters = ()

            if name:
                lookup_filters += ('name', name)
            if organization:
                lookup_filters += ('organization', organization)

            v = Gizmo().g.V().has(*lookup_filters)
            while v.hasNext():
                workspaces = Gizmo().g.V().has(*lookup_filters).elementMap('workspace_id',
                                                                           'organization', 'name').toList()
            else:
                raise VertexDoesNotExistException
            # return [v['name'][0] for v in Gizmo().g.V(self.v).outE('depends_on').has('redundant', 'true').inV().valueMap('name')]

        @classmethod
        def drop_all(cls):
            Gizmo().g.V().drop().iterate()

        @classmethod
        def all(cls):
            workspaces = []
            for v in Gizmo().g.V().hasLabel(Workspace.label).elementMap('workspace_id', 'name', 'organization', 'last_updated', 'created_at'):
                workspaces.append(
                    Workspace(
                        _id=v[T.id],
                        workspace_id=v['workspace_id'],
                        name=v['name'],
                        organization=v['organization'],
                        created_at=v['created_at'],
                        last_updated=v['last_updated'])
                )
            return workspaces

    @property
    def v(self):
        return Gizmo().g.V().has('workspace_id', self.workspace_id).next()

    @property
    def created_at_dt(self):
        return datetime.datetime.fromtimestamp(int(self.created_at))

    def get_total_revision_count(self):
        """Traverse the state revisions tree and count how many there are.

        Returns
            1 (the current_state_revision) + the count of succeeded (old) revisions.
        """
        try:
            v = Gizmo().g.V().hasLabel(Workspace.label).has('name', self.name).outE('has_current_state').inV().next()
            return 1 + Gizmo().g.V(v).repeat(outE('succeeded').inV()).emit().until(outE('succeeded').count().is_(0)).count().next()
        except StopIteration:
            return 0

    def get_first_revision(self):
        v = Gizmo().g.V().hasLabel(Workspace.label).has('name', self.name).outE('has_current_state').inV().next()
        r = Gizmo().g.V(v).repeat(outE('succeeded').inV()).until(outE('succeeded').count().is_(0)).elementMap().next()
        return State(
            _id=r[T.id],
            state_id=r['state_id'],
            resource_count=r['resource_count'],
            serial=r['serial'],
            created_at=r['created_at'],
            terraform_version=r['terraform_version']
        )

    def get_state_revisions(self):
        v = Gizmo().g.V().hasLabel(Workspace.label).has('name', self.name).outE('has_current_state').inV().next()
        results = Gizmo().g.V(v).repeat(outE('succeeded').inV()).emit().until(outE('succeeded').count().is_(0)).elementMap().toList()
        return [State(
            _id=v[T.id],
            state_id=v['state_id'],
            resource_count=v['resource_count'],
            serial=v['serial'],
            created_at=v['created_at'],
            terraform_version=v['terraform_version']
        ) for v in results]

    def get_upstreams(self, redundant_only=False):
        """Fetch a list of all Workspaces that this workspace is required by

        Args
            redundant_only: if True only return redundant dependencies.
        Returns
            A list of Workspace names for all upstream Workspaces that depend on this workspace.
        """
        redundant_str = str(redundant_only).lower()
        if redundant_only:
            return [v['name'][0] for v in Gizmo().g.V(self.v).inE('depends_on').has('redundant', redundant_str).outV().valueMap('name')]
        else:
            return [v['name'][0] for v in Gizmo().g.V(self.v).inE('depends_on').outV().valueMap('name')]

    def get_dependencies(self, redundant_only=False, required_only=False):
        """Fetch a list of all Workspaces that this Workspace has a direct dependency on.

        Args
            redundant_only: if True only return redundant dependencies.
            required_only: if True only return required dependencies (non redundant).
        Returns
            A list of Workspace names for all direct dependencies.
        """
        if redundant_only:
            return [v['name'][0] for v in Gizmo().g.V(self.v).outE('depends_on').has('redundant', 'true').inV().valueMap('name')]
        elif required_only:
            return [v['name'][0] for v in Gizmo().g.V(self.v).outE('depends_on').has('redundant', 'false').inV().valueMap('name')]
        else:
            return [v['name'][0] for v in Gizmo().g.V(self.v).outE('depends_on').inV().valueMap('name')]

    def remove_dependency(self, target):
        """Remove a depends_on link that exists between this Workspace and the target Workspace.

        Args
            target: the target Workspace representing the vertex that the depends_on edge connects this vertex to.
        """
        Gizmo().g.V(self.v).outE('depends_on').where(otherV().is_(target.v)).drop().iterate()
        self.save()

    def get_resources(self):
        """Follow out contains Edges and generate a list of Resources by creating a new object for each value in the
        returned list of element maps.

        Returns
            List of Resoure objects that belong to this workspace.
        """
        return [Resource(
            _id=v[T.id],
            name=v['name'],
            state_id=v['state_id'],
            resource_type=v['resource_type'],
            namespace=v['namespace'],
            last_updated=v['last_updated']
        ) for v in Gizmo().g.V().hasLabel(Workspace.label).has('workspace_id', self.workspace_id).outE('contains').inV().elementMap()]

    def get_resource_count(self):
        """Count the number of Resources Vertices that this Workspace depends on by counting the contains out Edges.
        """
        return Gizmo().g.V().has('workspace_id', self.workspace_id).outE('contains').count().next()

    def get_dependency_count(self, redundant=False):
        """Count the number of Workspace Vertices that this Workspace depends on by counting the depends_on out Edges.
        
        Returns
            An integer count of the total dependencies.
        """

        redundant_str = str(redundant).lower()
        return Gizmo().g.V().has('workspace_id', self.workspace_id).outE('depends_on').has('redundant', redundant_str).count().next()

    def get_chain(self, vertices_only=False):
        """Fetches the full chain (all nodes connected directly or indirectly) to the current node.
        Args
            vertices_only: if True only return all Vertices in the chain, ignoring paths.
        Returns
            A list of paths where each path is a link in the overall chain/network.
        """
        if not vertices_only:
            f =  [v for v in Gizmo().g.V().has('workspace_id', self.workspace_id).as_('from').emit().repeat(
                __.outE('depends_on').as_('e').inV().as_('to').dedup('from', 'e', 'to')).path().by(__.valueMap(True))]
        else:
            f =  [Workspace(
                _id=v[T.id],
                workspace_id=v['workspace_id'],
                name=v['name'],
                organization=v['organization'],
                last_updated=v['last_updated'],
                created_at=v['created_at']) for v in Gizmo().g.V().has('workspace_id', self.workspace_id).as_('from').repeat(
                __.outE('depends_on').inV().dedup()).emit().elementMap()]
            pass
        return f

    def get_current_state_revision(self):
        v = Gizmo().g.V().hasLabel(Workspace.label).has('workspace_id', self.workspace_id).outE('has_current_state').inV()
        while v.hasNext():
            r = Gizmo().g.V().hasLabel(Workspace.label).has('workspace_id', self.workspace_id).outE('has_current_state').inV().elementMap().toList()[0]
            return State(
                _id=r[T.id],
                state_id=r['state_id'],
                resource_count=r['resource_count'],
                serial=r['serial'],
                created_at=r['created_at'],
                terraform_version=r['terraform_version']
            )
        else:
            raise VertexDoesNotExistException

    def __init__(self, _id: int, workspace_id: str, name: str, organization: str, last_updated: str, created_at: str):
        self._id = _id
        self.workspace_id = workspace_id
        self.name = name
        self.organization = organization
        self.last_updated = last_updated
        self.created_at = created_at

    def depends_on(self, target, redundant=False):
        """Creates an edge from the current workspace to the target one.

        Args
            target: the target Workspace to set as the edge target node.
            redundant: the redundant property on the edge is set to this value (in lowercase form as a string).
        """
        redundant_str = str(redundant).lower()
        Gizmo().g.V(self.v).has('name', self.name).has('organization', self.organization).as_('v') \
            .V(target.v).has('name', target.name).has('organization', target.organization).as_('t') \
            .coalesce(
            __.inE('depends_on').where(__.outV().as_('v')),
            __.addE('depends_on').property('redundant', redundant_str).from_('v')
        ).next()
        self.save()

    def has_current_state(self, target):
        """Creates an edge to the current state version

        Args
            target: the target State to set as the new current state

        # TODO : This needs to also *remove* the current state, and set up the new has_revision....
        """

        first_time = False
        try:
            out_of_date_current_state_revision = self.get_current_state_revision()
        except VertexDoesNotExistException:
            # If the Workspace has no current state revision then it's the first time we're making one.
            first_time = True

        # Add the new current state revision edge to the new Vertex.
        Gizmo().g.V(self.v).as_('v') \
            .V(target.v).as_('t') \
            .coalesce(
            __.inE('has_current_state').where(__.outV().as_('v')),
            __.addE('has_current_state').from_('v')
        ).next()

        if not first_time:
            if out_of_date_current_state_revision.state_id != target.state_id:
                # If the current state doesn't equal the old one then we need to update
                # the edge to point to the correct, new current state revision.

                # Remove the current state edge that points to the old state revision Vertex.
                Gizmo().g.V(self.v).outE('has_current_state').where(otherV().is_(out_of_date_current_state_revision.v)).drop().iterate()

                # Add the succeeded edge between the new current state revision and the previous one.
                target.succeeded(out_of_date_current_state_revision)

        # Quick save to update last_updated.
        self.save()

    def delete(self):
        """Remove the Vertex that this Workspace represents from the database.
        """
        Gizmo().g.V(self.v).drop().iterate()

    def save(self):
        self.last_updated = str(datetime.datetime.utcnow().timestamp())
        Gizmo().g.V(self.v).property(Cardinality.single, 'last_updated', self.last_updated).next()
