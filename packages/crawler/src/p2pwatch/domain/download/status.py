"""A download as its client lists it."""

from dataclasses import dataclass

from p2pwatch.domain.download.states import FailureReason, WaitingReason
from p2pwatch.domain.file_key import FileKey


@dataclass(kw_only=True, frozen=True)
class DownloadStatus:
    """``completed`` is the client's own positive signal, never a byte count."""

    file: FileKey
    bytes_done: int
    size_bytes: int
    completed: bool
    waiting_reason: WaitingReason | None
    failure_reason: FailureReason | None
