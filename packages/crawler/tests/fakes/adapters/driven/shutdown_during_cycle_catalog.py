import asyncio

from p2pwatch.domain.download.candidate import DownloadCandidate
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader


class ShutdownDuringCycleCatalog(FakeDecisionReader):
    """Sets ``shutdown`` on the 1st ``read_download_candidates``, mid-cycle."""

    def __init__(self, shutdown: asyncio.Event) -> None:
        super().__init__()
        self._shutdown = shutdown

    def read_download_candidates(self) -> tuple[DownloadCandidate, ...]:
        self._shutdown.set()
        return ()
