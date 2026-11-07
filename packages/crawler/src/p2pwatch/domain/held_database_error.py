"""The error a database's opening raises while another process holds it, which the command line
prints in one line."""

from p2pwatch.domain.store_error import StoreError


class HeldDatabaseError(StoreError):
    """A database another process holds: refused at once by an exclusive opening, after the busy
    wait by any other."""
