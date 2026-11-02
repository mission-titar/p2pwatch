"""A source and a source name as their pages show them: the names a source carried, the sources
that carried a name, and their sharing periods."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.sharing_period import SharingPeriod
from p2pwatch.domain.source import SourceKey


@dataclass(kw_only=True, frozen=True)
class SourceNaming:
    """A source under one name it carried: its latest reading and its files under that name."""

    source: SourceKey
    source_name: str
    latest_seen_at: datetime
    file_count: int


@dataclass(kw_only=True, frozen=True)
class SourceHistory:
    """A source, the names read of it, its sharing periods over every file, their files' best
    filenames, of the most sourced observation, then the latest."""

    source: SourceKey
    source_namings: tuple[SourceNaming, ...]  # last seen first, then on source_name ascending
    sharing_periods: tuple[SharingPeriod, ...]  # the latest started first
    best_filename_by_file: Mapping[FileKey, str]  # every period's file


@dataclass(kw_only=True, frozen=True)
class SourceNameHistory:
    """A name, the sources read under it, its sharing periods without a user hash, their files'
    best filenames, of the most sourced observation, then the latest."""

    source_name: str
    source_namings: tuple[SourceNaming, ...]  # last seen first, then on source_id ascending
    sharing_periods: tuple[SharingPeriod, ...]  # the latest started first
    best_filename_by_file: Mapping[FileKey, str]  # every period's file
