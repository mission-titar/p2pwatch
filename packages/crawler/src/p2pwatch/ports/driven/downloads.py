"""Our tracked downloads, in ``local.db`` (never merged): their state, their target and when the
client last listed them."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from p2pwatch.domain.download.states import DownloadState, FailureReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey


class DownloadWriter(ABC):
    """Writes the tracked downloads' lifecycle."""

    @abstractmethod
    def record_queued(
        self, file: FileKey, target_id: str, size_bytes: int, queued_at: datetime
    ) -> bool:
        """Tracks ``file`` as queued; ``False`` when it is already tracked."""

    @abstractmethod
    def record_completed(self, file: FileKey, completed_at: datetime) -> None:
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
    def mark_seen(self, statuses: Iterable[DownloadStatus], seen_at: datetime) -> None:
        """Stamps each listed download ``seen_at``, with its waiting reason."""


class DownloadReader(ABC):
    """Reads the tracked downloads."""

    @abstractmethod
    def is_tracked(self, file: FileKey) -> bool:
        """Whether ``file`` has a row, whatever its state."""

    @abstractmethod
    def read_last_seen_at_by_file(self) -> dict[FileKey, datetime]:
        """When the client last listed each queued or downloading download."""

    @abstractmethod
    def read_tracked_states(self) -> dict[FileKey, DownloadState]:
        """Every tracked download's state."""

    @abstractmethod
    def read_queued_target_id(self, file: FileKey) -> str | None:
        """The target ``file`` was queued for, ``None`` when it is not tracked."""
