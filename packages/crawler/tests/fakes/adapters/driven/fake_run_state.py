from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.ports.driven.run_state_writer import RunStateWriter


class FakeRunState(RunStateWriter, RunStateReader):
    """Keeps each change by its method's name; reads ``paused``, which no change moves."""

    def __init__(self, *, paused: bool = False) -> None:
        self.changes: list[str] = []
        self.paused = paused

    def pause(self) -> None:
        self.changes.append("pause")

    def resume(self) -> None:
        self.changes.append("resume")

    def shut_down(self) -> None:
        self.changes.append("shut_down")

    def is_paused(self) -> bool:
        return self.paused
