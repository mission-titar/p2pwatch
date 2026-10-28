"""A source's sharing periods on a file, and the window a page reads them in."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.source import SourceKey, SourceRole


@dataclass(frozen=True)
class PeriodWindow:
    """The readings a page reads, ``since`` included to ``until`` excluded, and the longest gap
    within one period."""

    since: datetime
    until: datetime
    gap: timedelta


@dataclass(frozen=True)
class SharingPeriod:
    """One source's consecutive readings on one file by one node; only a sending period received
    bytes."""

    file: FileKey
    source: SourceKey | None  # None for a source without a user hash
    source_name: str | None
    role: SourceRole
    contact_point: str | None
    connectable: bool | None
    first_seen_at: datetime
    last_seen_at: datetime
    received_bytes: int
    node_id: NodeId  # the node that read it: a merged catalog holds several
