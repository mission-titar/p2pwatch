from p2pwatch_amule.application.ports.driving.port_sync_loop_runner import PortSyncLoopRunner
from p2pwatch_amule.domain.settings_error import SettingsError


class FakePortSyncLoopRunner(PortSyncLoopRunner):
    """Counts its runs, or raises a set error."""

    def __init__(self) -> None:
        self.error: SettingsError | None = None
        self.runs = 0

    def run_port_sync_loop(self) -> None:
        self.runs += 1
        if self.error is not None:
            raise self.error
