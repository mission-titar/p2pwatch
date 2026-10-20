"""A download's lifecycle on the crawler side: ``queued`` → ``downloading`` → ``completed``, or
``failed``; only ``queued`` and ``downloading`` count against the disk cap."""

from enum import StrEnum


class DownloadState(StrEnum):
    """A download's lifecycle on the crawler side (closed enum, spec §7)."""

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


class WaitingReason(StrEnum):
    """Why a download waits, shown to the operator: waiting is never failing."""

    DISK_FULL = "disk_full"
    PAUSED = "paused"
    LOCAL_PROCESSING = "local_processing"
    NO_SOURCE = "no_source"
    REMOTE_QUEUE = "remote_queue"


class FailureReason(StrEnum):
    """Why a download failed: ``ERROR`` is the client's, ``REJECTED`` and ``LOST`` the core's."""

    ERROR = "error"
    REJECTED = "rejected"
    LOST = "lost"
