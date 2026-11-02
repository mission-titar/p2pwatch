"""A catalogued file as a listing shows it, and the orders a listing sorts on."""

from dataclasses import dataclass
from enum import StrEnum

from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.observation import FileObservation


class CatalogEntrySort(StrEnum):
    """What a listing sorts on: the latest observation's filename, source count or instant, the
    file's size, or the strongest tier of its current decisions."""

    NAME = "name"
    SIZE = "size"
    SOURCES = "sources"
    LATEST_SEEN = "last_seen"  # the value keeps its old name: it is the URL's, in bookmarks
    TIER = "tier"


class SortDirection(StrEnum):
    """A file without the sort's value comes first ascending and last descending; ties go on
    ``file_id`` ascending either way."""

    ASC = "asc"
    DESC = "desc"


@dataclass(kw_only=True, frozen=True)
class CatalogEntry:
    """A file, its size, its latest observation and its current decisions, the legacy retraction
    of no target left out."""

    file: FileKey
    size_bytes: int
    latest_observation: FileObservation | None  # None before its first
    decisions: tuple[DecisionRecord, ...]  # one per target in target order, none retracted
