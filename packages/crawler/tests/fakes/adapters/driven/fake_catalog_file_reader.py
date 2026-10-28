from collections.abc import Mapping
from datetime import datetime

from catalog_matching.domain.decision_tier import DecisionTier
from p2pwatch.application.ports.driven.catalog_file_reader import CatalogFileReader
from p2pwatch.domain.catalog_entry import CatalogEntry, CatalogEntrySort, SortDirection
from p2pwatch.domain.file_history import FileHistory
from p2pwatch.domain.identifiers import FileId


class FakeCatalogFileReader(CatalogFileReader):
    """Reads what it is given, and keeps each call by its operation's name, with its arguments."""

    def __init__(
        self,
        *,
        catalog_entries: tuple[CatalogEntry, ...] = (),
        matched_and_total_file_counts: tuple[int, int] = (0, 0),
        file_count_by_tier: Mapping[DecisionTier, int] | None = None,
        file_history: FileHistory | None = None,
    ) -> None:
        self._catalog_entries = catalog_entries
        self._matched_and_total_file_counts = matched_and_total_file_counts
        self._file_count_by_tier = file_count_by_tier or {}
        self._file_history = file_history
        self.calls: list[tuple[str, dict[str, object]]] = []

    def read_catalog_entries(
        self,
        *,
        target_id: str | None,
        tier: DecisionTier | None,
        search_text: str | None,
        matched_only: bool,
        sort: CatalogEntrySort,
        direction: SortDirection,
        limit: int,
        offset: int,
    ) -> tuple[CatalogEntry, ...]:
        arguments: dict[str, object] = {
            "target_id": target_id,
            "tier": tier,
            "search_text": search_text,
            "matched_only": matched_only,
            "sort": sort,
            "direction": direction,
            "limit": limit,
            "offset": offset,
        }
        self.calls.append(("read_catalog_entries", arguments))
        return self._catalog_entries

    def read_matched_and_total_file_counts(
        self, *, target_id: str | None, tier: DecisionTier | None, search_text: str | None
    ) -> tuple[int, int]:
        arguments: dict[str, object] = {
            "target_id": target_id,
            "tier": tier,
            "search_text": search_text,
        }
        self.calls.append(("read_matched_and_total_file_counts", arguments))
        return self._matched_and_total_file_counts

    def read_file_count_by_tier(
        self, *, target_id: str | None, search_text: str | None
    ) -> Mapping[DecisionTier, int]:
        arguments: dict[str, object] = {"target_id": target_id, "search_text": search_text}
        self.calls.append(("read_file_count_by_tier", arguments))
        return self._file_count_by_tier

    def read_file_history(
        self, file_id: FileId, *, since: datetime, until: datetime
    ) -> FileHistory | None:
        arguments: dict[str, object] = {"file_id": file_id, "since": since, "until": until}
        self.calls.append(("read_file_history", arguments))
        return self._file_history
