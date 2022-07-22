from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import __, both, bothE, out, outE, path
from gremlin_python.process.traversal import T

from cartographer.gizmo import Gizmo
from cartographer.gizmo.models.exceptions import VertexDoesNotExistException, MultipleVerticesFoundException


class Vertex:
    """Base Vertex with a base vertices class that contains some common functionality
    like counting, fetching maximums and summing. When implementing with this as a Base class
    make sure to do the same for the vertcies nested class in the new child class."""
    label = None

    class vertices:
        label = None

        @classmethod
        def count_by(cls, group_by: str, **kwargs):
            """Returns the count for any given prop across all Vertices of this type
            in the database.

            Args
                group_by: the property to get the grouped counts for.
                kwargs: any number of .has() filters to apply to the base query.
            Returns
                An map of counts for the given property.
            """
            base_query = Gizmo().g.V().hasLabel(cls.label)
            for k, v in kwargs.items():
                base_query = base_query.has(k, v)
            
            return base_query.groupCount().by(group_by).next()

        @classmethod
        def sum(cls, prop):
            """Returns the sum of the stored value for any given prop across all Vertices of this type
            in the database.

            Args
                prop: the property to get the sum value for.
            Returns
                An integer sum of the given property.
            """
            return Gizmo().g.V().hasLabel(cls.label).properties(prop).value().sum().next()

        @classmethod
        def count(cls, **kwargs):
            """Takes any number of .has() arguments via kwargs and performs a count().
            Args
                kwargs: any number of .has() filters to apply to the base query.
            Returns
                An integer count of the current Vertex type with the has() filters applied.
            """
            base_query = Gizmo().g.V().hasLabel(cls.label)

            for k, v in kwargs.items():
                base_query = base_query.has(k, v)

            return base_query.count().next()

        @classmethod
        def max(cls, prop : str):
            """Returns the maximum stored value for any given prop across all Vertices of this type
            in the database.

            Args
                prop: the property to get the max value for.
            
            Returns
                An integer maximum of the given property.
            """
            return Gizmo().g.V().hasLabel(cls.label).values(prop).max().next()

        @classmethod
        def exists(cls, **kwargs):
            """Determine whether or not the Vertex exists with the given .has() filters.
            Args
                kwargs: any number of .has() filters to apply to the base query.
            Returns
                True if a Vertex is found, False if none found.
            """
            base_query = Gizmo().g.V().hasLabel(cls.label)
            for k, v in kwargs.items():
                base_query = base_query.has(k, v)

            return base_query.elementMap().hasNext()
