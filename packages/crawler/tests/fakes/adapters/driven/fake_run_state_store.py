from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.ports.driven.run_state_writer import RunStateWriter


class FakeRunStateStore(RunStateWriter, RunStateReader):
    """Reads back at once what it was set to, where the real store waits for the crawler's loop."""

    def __init__(self, *, paused: bool = False) -> None:
        self._paused = paused
        self.shutdown_requested = False

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def set_shutdown_requested(self) -> None:
        self.shutdown_requested = True

    def is_paused(self) -> bool:
        return self._paused
