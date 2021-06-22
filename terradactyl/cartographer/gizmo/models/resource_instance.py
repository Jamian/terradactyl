import datetime

from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import __, both, bothE, out, path
from gremlin_python.process.traversal import T

from cartographer.gizmo import Gizmo
from cartographer.gizmo.models import Vertex
from cartographer.gizmo.models.exceptions import VertexDoesNotExistException, MultipleVerticesFoundException

LABEL = 'resource_instance'
class ResourceInstance(Vertex):
    """Represents an instance of a Terraform Resource the graph database.
    """
    label = LABEL
    class vertices(Vertex.vertices):
        label = LABEL

        @classmethod
        def create(cls, state_id: str, index_key: str, resource_type: str):
            last_updated = str(datetime.datetime.utcnow().timestamp())
            v = Gizmo().g.addV(ResourceInstance.label) \
                .property('index_key', index_key) \
                .property('state_id', state_id) \
                .property('resource_type', resource_type) \
                .property('last_updated', last_updated).next()
            return ResourceInstance(v.id, state_id, index_key, resource_type, last_updated)

        @classmethod
        def get(cls, **kwargs):
            """Fetch a vertex where the given kwargs are has() filters that are dynamically concatenated to build
            out the Gremlin query. E.g. where kwargs equals : {'name', 'bar', 'age', '12'} the query becomes
            Gizmo().g.V().has('name', 'bar').has('age', '12')

            Returns a new ResourceInstance.
            """
            base_query = Gizmo().g.V().hasLabel(ResourceInstance.label)
            for k, v in kwargs.items():
                base_query = base_query.has(k, v)

            if not ResourceInstance.vertices.exists(**kwargs):
                raise VertexDoesNotExistException
            else:
                element_map = base_query.elementMap().next()
                # TODO : Returned more than one error
                return ResourceInstance(
                    _id=element_map[T.id],
                    index_key=element_map['index_key'],
                    state_id=element_map['state_id'],
                    resource_type=element_map['resource_type'],
                    last_updated=element_map['last_updated']
                )

        @classmethod
        def update_or_create(cls, state_id: str, index_key: str, resource_type: str):
            try:
                r = ResourceInstance.vertices.get(
                    index_key=index_key,
                    state_id=state_id,
                    resource_type=resource_type)
                r.state_id = state_id
                r.index_key = index_key
                r.resource_type = resource_type
                r.save()
            except VertexDoesNotExistException:
                r = ResourceInstance.vertices.create(
                    index_key=index_key,
                    state_id=state_id,
                    resource_type=resource_type
                )
            return r

    @property
    def v(self):
        return Gizmo().g.V().hasLabel(ResourceInstance.label).has('state_id', self.state_id).has('index_key', self.index_key).has('resource_type', self.resource_type).next()

    def __init__(self, _id: int, state_id: str, index_key: str, resource_type: str, last_updated: str = None):
        self._id = _id
        self.state_id = state_id
        self.index_key = index_key
        self.resource_type = resource_type
        if last_updated:
            self.last_updated = last_updated

    def instance_of(self, target):
        """Creates an edge from the current Resource Instance to the target one.

        Args
            target: the parent Resource Vertex that this is an instance of.
        """
        Gizmo().g.V(self.v).as_('v') \
            .V(target.v).as_('t') \
            .coalesce(
            __.inE('instance_of').where(__.outV().as_('v')),
            __.addE('instance_of').from_('v')
        ).next()

    def save(self):
        self.last_updated = str(datetime.datetime.utcnow().timestamp())
        Gizmo().g.V(self.v) \
            .property('state_id', self.state_id) \
            .property('resource_type', self.resource_type) \
            .property('index_key', self.index_key) \
            .property('last_updated', self.last_updated).next()
