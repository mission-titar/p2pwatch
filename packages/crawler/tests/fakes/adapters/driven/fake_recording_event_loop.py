from typing import Protocol


class LoopCallback(Protocol):
    def __call__(self) -> None: ...


class FakeRecordingEventLoop:
    """Fake loop that RECORDS scheduled callbacks WITHOUT running them (deferral proof)."""

    def __init__(self) -> None:
        self.callbacks: list[LoopCallback] = []

    def call_soon_threadsafe(self, callback: LoopCallback) -> None:
        self.callbacks.append(callback)
