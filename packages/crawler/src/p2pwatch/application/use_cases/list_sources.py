"""Lists the catalog's sources a page at a time, with the count the sources page shows."""

from p2pwatch.application.ports.driven.source_reader import SourceReader
from p2pwatch.application.ports.driving.source_lister import SourceLister, SourceListing
from p2pwatch.domain.paging import PAGE_SIZE


class ListSources(SourceLister):
    def __init__(self, source_reader: SourceReader) -> None:
        self._source_reader = source_reader

    def list_sources(self, *, search_text: str | None, page: int) -> SourceListing:
        known_sources = self._source_reader.read_known_sources(
            search_text=search_text, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE
        )
        return SourceListing(
            known_sources=known_sources,
            # A full page offers the next one, even when it turns out empty.
            has_next_page=len(known_sources) >= PAGE_SIZE,
            source_count=self._source_reader.read_source_count(search_text=search_text),
        )
