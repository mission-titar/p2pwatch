"""``TrackedDownloadWriter``: our tracked downloads, in ``local.db``, never merged."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from p2pwatch.domain.download.states import DownloadState, FailureReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey


class TrackedDownloadWriter(ABC):
    """Writes the tracked downloads' lifecycle."""

    @abstractmethod
    def record_queued(
        self, file: FileKey, target_id: str, size_bytes: int, queued_at: datetime
    ) -> None:
        """Tracks ``file`` as queued; a file already tracked keeps its row."""

    @abstractmethod
    def set_completed(self, file: FileKey, completed_at: datetime) -> None:
        """Marks ``file`` completed."""

    @abstractmethod
    def set_state(
        self,
        file: FileKey,
        state: Literal[DownloadState.DOWNLOADING, DownloadState.FAILED],
        failure_reason: FailureReason | None = None,
    ) -> None:
        """Moves ``file`` to ``state``, with its failure reason."""

    @abstractmethod
    def set_seen(self, statuses: Iterable[DownloadStatus], seen_at: datetime) -> None:
        """Stamps each listed download ``seen_at``, with its waiting reason; a file listed but not
        tracked stays untracked, without error."""
