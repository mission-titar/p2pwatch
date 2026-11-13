"""The error the filesystem's ports raise, in the domain since both sides use it."""

from p2pwatch.domain.declared_failure import DeclaredFailure


class InaccessiblePathError(DeclaredFailure):
    """A path the filesystem refuses to examine: removed, under a file, behind a directory it
    cannot search, its name too long."""
