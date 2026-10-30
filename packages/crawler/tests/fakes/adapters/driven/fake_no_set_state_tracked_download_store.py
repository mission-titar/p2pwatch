from typing import Literal

from p2pwatch.domain.download.states import DownloadState, FailureReason
from p2pwatch.domain.file_key import FileKey
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore


class FakeNoSetStateTrackedDownloadStore(FakeTrackedDownloadStore):
    """Fails the test on any state change."""

    def set_state(
        self,
        file: FileKey,
        *,
        state: Literal[DownloadState.DOWNLOADING, DownloadState.FAILED],
        failure_reason: FailureReason | None = None,
    ) -> None:
        raise AssertionError("set_state must not be called")
