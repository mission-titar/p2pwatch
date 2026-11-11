"""The stores' error type (spec orchestration §4/§7), in the domain since both sides
use it: the SQLite adapter's ``PersistenceError`` inherits it, the application catches it."""

from p2pwatch.domain.declared_failure import DeclaredFailure


class StoreError(DeclaredFailure):
    """Persistence failure reported by a store, a write its storage refuses (full, read-only)
    included (the adapter reports, it does not decide)."""
