"""``ListFiles``: a page of the catalog's files and their counts, in one read."""

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.application.ports.driven.catalog_file_reader import CatalogFileReader
from p2pwatch.application.ports.driving.file_lister import FileListing
from p2pwatch.application.use_cases.list_files import ListFiles
from p2pwatch.application.use_cases.paging import PAGE_SIZE
from p2pwatch.domain.catalog_entry import CatalogEntry, CatalogEntrySort, SortDirection
from p2pwatch.domain.file_key import FileKey, Network
from tests.fakes.adapters.driven.fake_catalog_file_reader import FakeCatalogFileReader

_ENTRY = CatalogEntry(
    file=FileKey(Network.ED2K, "a" * 32),
    size_bytes=100,
    latest_observation=None,
    decisions=(DecisionRecord("062A", "rule", DecisionTier.DOWNLOAD),),
)


def _reader(entry_count: int = 1) -> FakeCatalogFileReader:
    """Reads ``entry_count`` copies of one entry."""
    return FakeCatalogFileReader(
        catalog_entries=(_ENTRY,) * entry_count,
        matched_and_total_file_counts=(3, 7),
        file_count_by_tier={"download": 3},
    )


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
    reader = _reader()

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
    reader = _reader()

    _list_files(reader, page=3)

    assert reader.calls[0][1]["offset"] == 2 * PAGE_SIZE == 100


def test_only_a_full_page_offers_a_next_one() -> None:
    assert _list_files(_reader(PAGE_SIZE)).has_next_page
    assert not _list_files(_reader(PAGE_SIZE - 1)).has_next_page
