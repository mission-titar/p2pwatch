from collections.abc import Mapping
from typing import Any

from p2pwatch.application.ports.driven.catalog_file_reader import CatalogFileReader
from p2pwatch.domain.catalog_entry import CatalogEntry
from p2pwatch.domain.file_history import FileHistory


class FakeCatalogFileReader(CatalogFileReader):
    """Reads what it is given, and keeps each call by its operation's name, with its arguments."""

    def __init__(
        self,
        *,
        catalog_entries: tuple[CatalogEntry, ...] = (),
        matched_and_total_file_counts: tuple[int, int] = (0, 0),
        file_count_by_tier: Mapping[str, int] | None = None,
        file_history: FileHistory | None = None,
    ) -> None:
        self._catalog_entries = catalog_entries
        self._matched_and_total_file_counts = matched_and_total_file_counts
        self._file_count_by_tier = file_count_by_tier or {}
        self._file_history = file_history
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def read_catalog_entries(self, **arguments: Any) -> tuple[CatalogEntry, ...]:
        self.calls.append(("read_catalog_entries", arguments))
        return self._catalog_entries

    def read_matched_and_total_file_counts(self, **arguments: Any) -> tuple[int, int]:
        self.calls.append(("read_matched_and_total_file_counts", arguments))
        return self._matched_and_total_file_counts

    def read_file_count_by_tier(self, **arguments: Any) -> Mapping[str, int]:
        self.calls.append(("read_file_count_by_tier", arguments))
        return self._file_count_by_tier

    def read_file_history(self, file_id: bytes, **arguments: Any) -> FileHistory | None:
        self.calls.append(("read_file_history", {"file_id": file_id, **arguments}))
        return self._file_history
