class ListenPortError(Exception):
    """amuled's API did not set its listen ports, its message saying why."""


class ApiNotReadyError(ListenPortError):
    """amuled's API cannot serve yet: not listening, without its first snapshot, or refusing a
    fresh token."""


class ListenPortRejectedError(ListenPortError):
    """amuled refused the port, kept on its previous one: out of range, held, or its EC port."""
