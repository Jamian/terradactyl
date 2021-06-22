class VertexDoesNotExistException(Exception):
    """Raised when a Vertex lookup fails to find the Vertex. Useful to controlling
    when something like a hasNext() is returning False. Raise this rather than a
    allowing a StopIteration error to occurr.
    """
    pass

class MultipleVerticesFoundException(Exception):
    """Raised when searching for a single Vertex returns more than one.
    For example when using the Vertex.vertices.get() call. Allows the calling
    function to handle how they want to deal with this particular event.
    """
    pass