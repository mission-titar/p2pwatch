"""The stores' error type, in the domain since both sides
use it: the SQLite adapter's ``PersistenceError`` inherits it, the application catches it."""

from p2pwatch.domain.expected_error import ExpectedError


class StoreError(ExpectedError):
    """Persistence failure reported by a store, a write its storage refuses (full, read-only)
    included (the adapter reports, it does not decide)."""
