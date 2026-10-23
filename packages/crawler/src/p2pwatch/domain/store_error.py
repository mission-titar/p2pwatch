"""Error contract of the stores (spec orchestration §4/§7), in the domain since both sides
use it: the SQLite adapter's ``PersistenceError`` inherits it, the application catches it."""


class StoreError(Exception):
    """Persistence failure reported by a store (the adapter reports, it does not decide)."""
