class DeclaredFailure(Exception):
    """A failure the code expects, named by its subclass: the reason an outcome failed. An exception
    so that ports can raise one too; a status reading records one without raising it."""
