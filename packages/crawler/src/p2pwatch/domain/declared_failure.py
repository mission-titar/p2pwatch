"""The base of every failure a driven port declares, so a failure is told from a bug by its type."""


class DeclaredFailure(Exception):
    """A failure a driven port declares, its outside system's (the network, the client, the disk);
    any other exception is a bug."""
