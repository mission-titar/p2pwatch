"""The base of every failure a contract names (spec v5 lot 4, D3), in the domain since both sides
use it."""


class DeclaredFailure(Exception):
    """A failure a contract names: an outcome's reason, raised by a port or carried by a reading
    that raises nothing."""
