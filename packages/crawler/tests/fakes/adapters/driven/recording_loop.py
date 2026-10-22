from collections.abc import Callable


class RecordingLoop:
    """Fake loop that RECORDS scheduled callbacks WITHOUT running them (deferral proof)."""

    def __init__(self) -> None:
        self.callbacks: list[Callable[[], None]] = []

    def call_soon_threadsafe(self, callback: Callable[[], None]) -> None:
        self.callbacks.append(callback)
