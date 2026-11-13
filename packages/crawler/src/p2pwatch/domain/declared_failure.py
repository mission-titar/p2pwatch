class DeclaredFailure(Exception):
    """A failure the code expects, such as aMule not answering, as opposed to a bug. An exception,
    so that the errors the aMule client raises can later be recorded the same way."""
