"""``ListFiles``: a page of the catalog's files and their counts, in one read."""

from collections.abc import Mapping
from typing import Any

from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.application.list_files import ListFiles
from p2pwatch.domain.catalog_entry import CatalogEntry, CatalogEntrySort, SortDirection
from p2pwatch.domain.file_history import FileHistory
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.paging import PAGE_SIZE
from p2pwatch.ports.driven.catalog_file_reader import CatalogFileReader
from p2pwatch.ports.driving.file_lister import FileListing

_ENTRY = CatalogEntry(
    file=FileKey(Network.ED2K, "a" * 32),
    size_bytes=100,
    latest_observation=None,
    decisions=(DecisionRecord("062A", "rule", "download"),),
)


class _FakeCatalogFileReader(CatalogFileReader):
    """Reads ``entry_count`` copies of one entry, and keeps each call's arguments."""

    def __init__(self, entry_count: int = 1) -> None:
        self._entry_count = entry_count
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def read_catalog_entries(self, **arguments: Any) -> tuple[CatalogEntry, ...]:
        self.calls.append(("read_catalog_entries", arguments))
        return (_ENTRY,) * self._entry_count

    def read_matched_and_total_file_counts(self, **arguments: Any) -> tuple[int, int]:
        self.calls.append(("read_matched_and_total_file_counts", arguments))
        return 3, 7

    def read_file_count_by_tier(self, **arguments: Any) -> Mapping[str, int]:
        self.calls.append(("read_file_count_by_tier", arguments))
        return {"download": 3}

    def read_file_history(self, file_id: bytes, **arguments: Any) -> FileHistory | None:
        raise AssertionError("ListFiles reads no file history")


def _list_files(reader: CatalogFileReader, *, page: int = 1) -> FileListing:
    return ListFiles(reader).list_files(
        target_id="062A",
        tier="download",
        search_text="keroro",
        matched_only=True,
        sort=CatalogEntrySort.SIZE,
        direction=SortDirection.ASC,
        page=page,
    )


def test_the_listing_holds_the_page_read_and_the_counts_of_the_files_passing_the_filters() -> None:
    reader = _FakeCatalogFileReader()

    listing = _list_files(reader)

    assert listing == FileListing(
        catalog_entries=(_ENTRY,),
        has_next_page=False,
        matched_file_count=3,
        total_file_count=7,
        file_count_by_tier={"download": 3},
    )
    assert reader.calls == [
        (
            "read_catalog_entries",
            {
                "target_id": "062A",
                "tier": "download",
                "search_text": "keroro",
                "matched_only": True,
                "sort": CatalogEntrySort.SIZE,
                "direction": SortDirection.ASC,
                "limit": PAGE_SIZE,
                "offset": 0,
            },
        ),
        (
            "read_matched_and_total_file_counts",
            {"target_id": "062A", "tier": "download", "search_text": "keroro"},
        ),
        ("read_file_count_by_tier", {"target_id": "062A", "search_text": "keroro"}),
    ]


def test_a_page_starts_after_the_files_of_the_pages_before_it() -> None:
    reader = _FakeCatalogFileReader()

    _list_files(reader, page=3)

    assert reader.calls[0][1]["offset"] == 2 * PAGE_SIZE == 100


def test_only_a_full_page_offers_a_next_one() -> None:
    assert _list_files(_FakeCatalogFileReader(PAGE_SIZE)).has_next_page
    assert not _list_files(_FakeCatalogFileReader(PAGE_SIZE - 1)).has_next_page
