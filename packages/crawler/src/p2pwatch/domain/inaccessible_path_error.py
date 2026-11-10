"""The error the filesystem's ports raise, in the domain since both sides use it."""


class InaccessiblePathError(Exception):
    """A path the filesystem refuses to examine: removed, under a file, behind a directory it
    cannot search, its name too long."""
