import datetime

from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import __, both, bothE, out, path
from gremlin_python.process.traversal import T

from cartographer.gizmo import Gizmo
from cartographer.gizmo.models import Vertex
from cartographer.gizmo.models.resource_instance import ResourceInstance
from cartographer.gizmo.models.exceptions import VertexDoesNotExistException, MultipleVerticesFoundException

LABEL = 'resource'
class Resource(Vertex):
    """Represents a Terraform Resource in the graph database.
    """
    label = LABEL
    class vertices(Vertex.vertices):
        label = LABEL

        @classmethod
        def create(cls, state_id: str, name: str, resource_type: str, namespace: str, mode: str):
            last_updated = str(datetime.datetime.utcnow().timestamp())
            v = Gizmo().g.addV(Resource.label) \
                .property('state_id', state_id) \
                .property('name', name) \
                .property('resource_type', resource_type) \
                .property('namespace', namespace) \
                .property('mode', mode) \
                .property('last_updated', last_updated).next()
            return Resource(
                _id=v.id,
                state_id=state_id,
                name=name,
                resource_type=resource_type,
                namespace=namespace,
                mode=mode,
                last_updated=last_updated)

        @classmethod
        def get(cls, **kwargs):
            """Fetch a vertex where the given kwargs are has() filters that are dynamically concatenated to build
            out the Gremlin query. E.g. where kwargs equals : {'name', 'bar', 'age', '12'} the query becomes
            Gizmo().g.V().has('name', 'bar').has('age', '12')

            Returns a new Resource.
            """
            base_query = Gizmo().g.V().hasLabel(Resource.label)
            for k, v in kwargs.items():
                base_query = base_query.has(k, v)

            if not Resource.vertices.exists(**kwargs):
                raise VertexDoesNotExistException
            else:
                element_map = base_query.elementMap().next()
                # TODO : Returned more than one error
                return Resource(
                    _id=element_map[T.id],
                    name=element_map['name'],
                    state_id=element_map['state_id'],
                    resource_type=element_map['resource_type'],
                    namespace=element_map['namespace'],
                    mode=element_map['mode'],
                    last_updated=element_map['last_updated']
                )

        @classmethod
        def update_or_create(cls, state_id: str, name: str, resource_type: str, namespace: str, mode: str):
            try:
                # TODO : This doesn't work for update - just get for now. Nothing to actually update on these.
                r = Resource.vertices.get(
                    state_id=state_id,
                    name=name,
                    namespace=namespace,
                    resource_type=resource_type,
                    mode=mode)
            except VertexDoesNotExistException:
                r = Resource.vertices.create(
                    state_id=state_id,
                    name=name,
                    namespace=namespace,
                    resource_type=resource_type,
                    mode=mode
                )
            return r

    @property
    def v(self):
        return Gizmo().g.V().has('state_id', self.state_id).has('namespace', self.namespace).has('resource_type', self.resource_type).next()

    def __init__(self, _id: int, state_id: str, name: str, resource_type: str, namespace: str, mode: str, last_updated: str = None):
        self._id = _id
        self.state_id = state_id
        self.name = name
        self.resource_type = resource_type
        self.namespace = namespace
        self.mode = mode
        if last_updated:
            self.last_updated = last_updated

    def depends_on(self, target):
        """Creates an edge from the current resource to the target one.

        Args:
            target: the Resource object that this Resource depends on.
        """
        try:
            Gizmo().g.V(self.v).has('namespace', self.namespace).has('state_id', self.state_id).as_('v') \
                .V(target.v).has('namespace', target.namespace).has('state_id', target.state_id).as_('t') \
                .coalesce(
                __.inE('r_depends_on').where(__.outV().as_('v')),
                __.addE('r_depends_on').from_('v')
            ).next()
        except:
            print(f'failed to add r_depends_on from {self.namespace} to {target.namespace}')
        self.save()

    def get_dependencies(self):
        """Fetch a list of names of the Resource that this Resource depends on.
        """
        return [v['name'][0] for v in Gizmo().g.V(self.v).outE('r_depends_on').inV().valueMap('name')]

    def get_instances(self):
        """Feth a list of ResourceInstance that this Resource is implemented by.
        """
        return [ResourceInstance(
            index_key=r['index_key'],
            state_id=r['state_id'],
            resource_type=r['resource_type']
        ) for r in Gizmo().g.V().hasLabel(ResourceInstance.label).outE('instance_of').inV(self.v).valueMap()]

    def save(self):
        self.last_updated = str(datetime.datetime.utcnow().timestamp())
        Gizmo().g.V(self.v) \
            .property('state_id', self.state_id) \
            .property('resource_type', self.resource_type) \
            .property('namespace', self.namespace) \
            .property('mode', self.mode) \
            .property('last_updated', self.last_updated).next()
