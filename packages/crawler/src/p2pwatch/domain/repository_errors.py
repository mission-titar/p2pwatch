"""Error contract of the repositories (spec orchestration §4/§7), in the domain since both sides
use it: the SQLite adapter's ``PersistenceError`` inherits it, the application catches it."""


class RepositoryError(Exception):
    """Persistence failure reported by a repository (the adapter reports, it does not decide)."""
