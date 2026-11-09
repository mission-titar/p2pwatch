"""The error the crawler raises once its shutdown deadline cut the unwind or the close, which the
command line reports as the clean stop it still is."""


class ShutdownDeadlineError(Exception):
    """The shutdown deadline fired: a bound kept, never a ``TimeoutError`` raised elsewhere."""
