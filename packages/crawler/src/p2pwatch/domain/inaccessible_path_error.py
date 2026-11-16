"""The error the filesystem's ports raise, in the domain since both sides use it."""

from p2pwatch.domain.expected_error import ExpectedError


class InaccessiblePathError(ExpectedError):
    """A path the filesystem refuses to examine: removed, under a file, behind a directory it
    cannot search, its name too long."""
