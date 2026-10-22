from collections.abc import Callable


class FakeImmediateEventLoop:
    """Fake loop whose ``call_soon_threadsafe`` runs the callback INLINE."""

    def call_soon_threadsafe(self, callback: Callable[[], None]) -> None:
        callback()
