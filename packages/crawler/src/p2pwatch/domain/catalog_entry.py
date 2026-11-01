"""A catalogued file as a listing shows it, and the orders a listing sorts on."""

from dataclasses import dataclass
from enum import StrEnum

from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.observation import FileObservation


class CatalogEntrySort(StrEnum):
    NAME = "name"
    SIZE = "size"
    SOURCES = "sources"
    LATEST_SEEN = "last_seen"  # the value keeps its old name: it is the URL's, in bookmarks
    TIER = "tier"  # the strongest tier of the file's current decisions


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


@dataclass(kw_only=True, frozen=True)
class CatalogEntry:
    """A file, the size it was first observed with, its latest observation (``None`` before its
    first) and its current decisions, one per target, in target order; a retracted target has
    none, the legacy ``target_id=""`` sentinel is none."""

    file: FileKey
    size_bytes: int
    latest_observation: FileObservation | None
    decisions: tuple[DecisionRecord, ...]
