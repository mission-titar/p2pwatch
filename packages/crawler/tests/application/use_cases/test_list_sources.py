"""``ListSources``: a page of the catalog's sources and their count, in one read."""

from datetime import UTC, datetime

from p2pwatch.application.ports.driven.source_reader import SourceReader
from p2pwatch.application.ports.driving.source_lister import SourceListing
from p2pwatch.application.use_cases.list_sources import ListSources
from p2pwatch.application.use_cases.paging import PAGE_SIZE
from p2pwatch.domain.file_key import Network
from p2pwatch.domain.known_source import KnownSource
from p2pwatch.domain.source import SourceKey
from tests.fakes.adapters.driven.fake_source_reader import FakeSourceReader

_KNOWN_SOURCE = KnownSource(
    source=SourceKey(network=Network.ED2K, native_id="1f2e" * 8),
    source_name="AnimuseeFMR",
    latest_seen_at=datetime(2026, 10, 13, 20, tzinfo=UTC),
    file_count=2,
)


def _reader(known_source_count: int = 1) -> FakeSourceReader:
    """Reads ``known_source_count`` copies of one source, out of 7."""
    return FakeSourceReader(known_sources=(_KNOWN_SOURCE,) * known_source_count, source_count=7)


def _list_sources(reader: SourceReader, *, page: int = 1) -> SourceListing:
    return ListSources(reader).list_sources(search_text="FMR", page=page)


def test_the_listing_holds_the_page_read_and_the_count_of_the_sources_passing_the_search() -> None:
    reader = _reader()

    listing = _list_sources(reader)

    assert listing == SourceListing(
        known_sources=(_KNOWN_SOURCE,), has_next_page=False, source_count=7
    )
    assert reader.calls == [
        ("read_known_sources", {"search_text": "FMR", "limit": PAGE_SIZE, "offset": 0}),
        ("read_source_count", {"search_text": "FMR"}),
    ]


def test_a_page_starts_after_the_sources_of_the_pages_before_it() -> None:
    reader = _reader()

    _list_sources(reader, page=3)

    assert reader.calls[0][1]["offset"] == 2 * PAGE_SIZE == 100


def test_only_a_full_page_offers_a_next_one() -> None:
    assert _list_sources(_reader(PAGE_SIZE)).has_next_page
    assert not _list_sources(_reader(PAGE_SIZE - 1)).has_next_page
