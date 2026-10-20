"""A source and a source name as their pages show them: the names a source carried, the sources
that carried a name, and their sharing periods."""

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


@dataclass(frozen=True)
class SourceNameHistory:
    """A name, the sources read under it, last seen first, its sharing periods without a user
    hash, newest first, and the best filename of each of their files ever seen."""

    source_name: str
    source_namings: tuple[SourceNaming, ...]
    sharing_periods: tuple[SharingPeriod, ...]
    best_filename_by_file: Mapping[FileKey, str]
