from p2pwatch.application.ports.driven.run_state_writer import RunStateWriter
from p2pwatch.domain.download.candidate import DownloadCandidate
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader


class FakeShutdownDuringCycleDecisionReader(FakeDecisionReader):
    """Requests the shutdown on the 1st ``read_download_candidates``, mid-cycle."""

    def __init__(self, run_state: RunStateWriter) -> None:
        super().__init__()
        self._run_state = run_state

    def read_download_candidates(self) -> tuple[DownloadCandidate, ...]:
        self._run_state.set_shutdown_requested()
        return ()
