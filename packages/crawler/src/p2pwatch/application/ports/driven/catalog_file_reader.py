"""``CatalogFileReader``: reads the catalog's files."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import datetime

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.domain.catalog_entry import CatalogEntry, CatalogEntrySort, SortDirection
from p2pwatch.domain.file_history import FileHistory
from p2pwatch.domain.identifiers import FileId


class CatalogFileReader(ABC):
    """Reads the catalog from any thread. A file passes ``target_id`` when it holds a current
    decision of that target and a tier other than ``catalog``, ``tier`` when it holds one of that
    tier, ``search_text`` when its latest filename holds it as typed, case and accents ignored."""

    @abstractmethod
    def read_catalog_entries(
        self,
        *,
        target_id: TargetId | None,
        tier: DecisionTier | None,
        search_text: str | None,
        matched_only: bool,
        sort: CatalogEntrySort,
        direction: SortDirection,
        limit: int,
        offset: int,
    ) -> tuple[CatalogEntry, ...]:
        """The files passing the filters, ``matched_only`` keeping those with a current decision,
        sorted on ``sort`` in ``direction``, a file without its value first ascending and last
        descending, then on ``file_id`` ascending: at most ``limit`` of them from ``offset``."""

    @abstractmethod
    def read_matched_and_total_file_counts(
        self, *, target_id: TargetId | None, tier: DecisionTier | None, search_text: str | None
    ) -> tuple[int, int]:
        """Of the files passing the filters, how many hold a current decision, and how many in
        all."""

    @abstractmethod
    def read_file_count_by_tier(
        self, *, target_id: TargetId | None, search_text: str | None
    ) -> Mapping[DecisionTier, int]:
        """By tier, how many files passing the filters hold a current decision of that tier; a
        tier no file holds is absent, not 0."""

    @abstractmethod
    def read_file_history(
        self, file_id: FileId, *, since: datetime, until: datetime
    ) -> FileHistory | None:
        """The file's history, its observations from ``since`` included to ``until`` excluded;
        ``None`` for a file the catalog does not hold."""
