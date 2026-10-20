"""A source as its page shows it: the names it carried and its sharing periods (stage 4 spec,
D13)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.sharing_period import SharingPeriod
from p2pwatch.domain.source import SourceKey


@dataclass(frozen=True)
class SourceNaming:
    """A source under one name it carried: its latest reading and its files under that name."""

    source: SourceKey
    source_name: str
    last_seen_at: datetime
    file_count: int


@dataclass(frozen=True)
class SourceHistory:
    """A source, the names read of it, last seen first, its sharing periods over every file,
    newest first, and the best filename of each of their files ever seen."""

    source: SourceKey
    source_namings: tuple[SourceNaming, ...]
    sharing_periods: tuple[SharingPeriod, ...]
    best_filename_by_file: Mapping[FileKey, str]
