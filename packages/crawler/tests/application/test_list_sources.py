"""``ListSources``: a page of the catalog's sources and their count, in one read."""

from datetime import UTC, datetime
from typing import Any

from p2pwatch.application.list_sources import ListSources
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.known_source import KnownSource
from p2pwatch.domain.paging import PAGE_SIZE
from p2pwatch.domain.sharing_period import PeriodWindow, SharingPeriod
from p2pwatch.domain.source import SourceKey
from p2pwatch.domain.source_history import SourceHistory, SourceNameHistory
from p2pwatch.ports.driven.source_reader import SourceReader
from p2pwatch.ports.driving.source_lister import SourceListing

_KNOWN_SOURCE = KnownSource(
    source=SourceKey(Network.ED2K, "1f2e" * 8),
    source_name="AnimuseeFMR",
    last_seen_at=datetime(2026, 10, 13, 20, tzinfo=UTC),
    file_count=2,
)


class _FakeSourceReader(SourceReader):
    """Reads ``known_source_count`` copies of one source, and keeps each call's arguments."""

    def __init__(self, known_source_count: int = 1) -> None:
        self._known_source_count = known_source_count
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def read_known_sources(self, **arguments: Any) -> tuple[KnownSource, ...]:
        self.calls.append(("read_known_sources", arguments))
        return (_KNOWN_SOURCE,) * self._known_source_count

    def read_source_count(self, **arguments: Any) -> int:
        self.calls.append(("read_source_count", arguments))
        return 7

    def read_source_history(self, source_id: bytes, **arguments: Any) -> SourceHistory | None:
        raise AssertionError("ListSources describes no source")

    def read_source_name_history(
        self, source_name: str, **arguments: Any
    ) -> SourceNameHistory | None:
        raise AssertionError("ListSources describes no source name")

    def read_sharing_periods(
        self, file: FileKey, window: PeriodWindow
    ) -> tuple[SharingPeriod, ...]:
        raise AssertionError("ListSources reads no sharing period")


def _list_sources(reader: SourceReader, *, page: int = 1) -> SourceListing:
    return ListSources(reader).list_sources(search_text="FMR", page=page)


def test_the_listing_holds_the_page_read_and_the_count_of_the_sources_passing_the_search() -> None:
    reader = _FakeSourceReader()

    listing = _list_sources(reader)

    assert listing == SourceListing(
        known_sources=(_KNOWN_SOURCE,), has_next_page=False, source_count=7
    )
    assert reader.calls == [
        ("read_known_sources", {"search_text": "FMR", "limit": PAGE_SIZE, "offset": 0}),
        ("read_source_count", {"search_text": "FMR"}),
    ]


def test_a_page_starts_after_the_sources_of_the_pages_before_it() -> None:
    reader = _FakeSourceReader()

    _list_sources(reader, page=3)

    assert reader.calls[0][1]["offset"] == 2 * PAGE_SIZE == 100


def test_only_a_full_page_offers_a_next_one() -> None:
    assert _list_sources(_FakeSourceReader(PAGE_SIZE)).has_next_page
    assert not _list_sources(_FakeSourceReader(PAGE_SIZE - 1)).has_next_page
