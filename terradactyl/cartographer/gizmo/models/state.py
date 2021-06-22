import datetime

from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import __, both, bothE, out, path
from gremlin_python.process.traversal import T

from cartographer.gizmo import Gizmo
from cartographer.gizmo.models import Vertex
from cartographer.gizmo.models.resource import Resource
from cartographer.gizmo.models.exceptions import VertexDoesNotExistException, MultipleVerticesFoundException

LABEL = 'state'

class State(Vertex):
    """Represents a State, including State Revisions in the graph database.
    """
    label = LABEL

    class vertices(Vertex.vertices):
        label = LABEL

        @classmethod
        def create(cls, state_id: str, resource_count: int, serial: int, created_at: str, terraform_version: str):
            """Create a new State Vertex
            created_at : the timestamp from Terraform Cloud for when the State was created. *Not* when it was created in Terradactyl.
            """
            last_updated = str(datetime.datetime.utcnow().timestamp())
            v = Gizmo().g.addV(State.label) \
                .property('state_id', state_id) \
                .property('resource_count', resource_count) \
                .property('serial', serial) \
                .property('terraform_version', terraform_version) \
                .property('created_at', created_at).next()
            return State(
                _id=v.id,
                state_id=state_id,
                resource_count=resource_count,
                serial=serial,
                terraform_version=terraform_version,
                created_at=created_at)

        @classmethod
        def update_or_create(cls, state_id: str, resource_count: int, serial: int, terraform_version: str, created_at: str):
            try:
                s = State.vertices.get(state_id=state_id)
                s.resource_count = resource_count
                s.save()
            except VertexDoesNotExistException:
                s = State.vertices.create(
                    state_id=state_id,
                    resource_count=resource_count,
                    serial=serial,
                    terraform_version=terraform_version,
                    created_at=created_at
                )
            return s

        @classmethod
        def get(cls, **kwargs):
            """Fetch a vertex where the given kwargs are has() filters that are dynamically concatenated to build
            out the Gremlin query. E.g. where kwargs equals : {'name', 'bar', 'age', '12'} the query becomes
            Gizmo().g.V().has('name', 'bar').has('age', '12')

            Returns a new State.
            """
            base_query = Gizmo().g.V().hasLabel(State.label)
            for k, v in kwargs.items():
                base_query = base_query.has(k, v)

            if not State.vertices.exists(**kwargs):
                raise VertexDoesNotExistException
            else:
                element_map = base_query.elementMap().next()
                # TODO : Returned more than one error
                return State(
                    _id=element_map[T.id],
                    state_id=element_map['state_id'],
                    created_at=element_map['created_at'],
                    terraform_version=element_map['terraform_version'],
                    serial=element_map['serial'],
                    resource_count=element_map['resource_count']
                )

    def __init__(self, _id: int, state_id: str, created_at: str, serial: int, resource_count: int, terraform_version: str):
        self._id = _id
        self.state_id = state_id
        self.created_at = created_at
        self.terraform_version = terraform_version
        self.serial = serial
        self.resource_count = resource_count

    @property
    def v(self):
        return Gizmo().g.V().hasLabel(State.label).has('state_id', self.state_id).next()

    @property
    def created_at_dt(self):
        return datetime.datetime.fromtimestamp(int(self.created_at))

    def succeeded(self, target):
        """Creates an edge from the current state to the previous one.
        TODO : Handle if current?
        """
        Gizmo().g.V(self.v).has('state_id', self.state_id).as_('v') \
            .V(target.v).has('state_id', target.state_id).as_('t') \
            .coalesce(
            __.inE('succeeded').where(__.outV().as_('v')),
            __.addE('succeeded').from_('v')
        ).next()

    def contains(self, target_resource):
        """Creates a edge from the current state to the target resource.
        """
        Gizmo().g.V(self.v).has('state_id', self.state_id).as_('v') \
            .V(target_resource.v).has('name', target_resource.name).has('resource_type', target_resource.resource_type).has('state_id', target_resource.state_id).as_('t') \
            .coalesce(
            __.inE('contains').where(__.outV().as_('v')),
            __.addE('contains').from_('v')
        ).next()

    def save(self):
        self.last_updated = str(datetime.datetime.utcnow().timestamp())
        Gizmo().g.V(self.v).has('state_id', self.state_id) \
            .property('terraform_version', self.terraform_version) \
            .property('serial', self.serial) \
            .property('resource_count', self.resource_count) \
            .property('last_updated', self.last_updated).next()
