"""``TrackedDownloadReader``: our tracked downloads, in ``local.db``, never merged: their state,
their target and when the client last listed them."""

from abc import ABC, abstractmethod
from datetime import datetime

from p2pwatch.domain.download.states import DownloadState
from p2pwatch.domain.file_key import FileKey


class TrackedDownloadReader(ABC):
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
