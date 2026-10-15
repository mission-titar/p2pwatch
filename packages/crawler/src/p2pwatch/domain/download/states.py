"""A download's lifecycle on the crawler side: ``queued`` → ``downloading`` → ``completed``, or
``failed``; only ``queued`` and ``downloading`` count against the disk cap."""

from enum import StrEnum


class DownloadState(StrEnum):
    """A download's lifecycle on the crawler side (closed enum, spec §7)."""

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
