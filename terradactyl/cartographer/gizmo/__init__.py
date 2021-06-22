from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.structure.graph import Graph

class Gizmo:
    _instance = None
    _graph = None
    g = None

    def __new__(cls, host: str="localhost", port: int=8182):
        if cls._instance is None:
            cls._graph = Graph()
            cls.g = cls._graph.traversal().withRemote(DriverRemoteConnection(f'ws://{host}:{port}/gremlin', 'g'))
            cls._instance = super(Gizmo, cls).__new__(cls)

        return cls._instance

    def count_edges(self, label, **kwargs):
        """
            Args
            group_by: the property to get the grouped counts for.
            kwargs: any number of .has() filters to apply to the base query.
        Returns
            An map of counts for the given property.
        """
        base_query = Gizmo().g.E().hasLabel(label)
        for k, v in kwargs.items():
            base_query = base_query.has(k, v)
        
        return base_query.count().next()
