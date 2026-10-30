from dataclasses import dataclass

from p2pwatch.application.ports.driving.source_lister import SourceLister, SourceListing


@dataclass(kw_only=True, frozen=True)
class ListSourcesCall:
    """The arguments of one ``list_sources`` call."""

    search_text: str | None
    page: int


class FakeSourceLister(SourceLister):
    """Lists the sources it is given, and keeps each call's arguments."""

    def __init__(self, source_listing: SourceListing) -> None:
        self._source_listing = source_listing
        self.calls: list[ListSourcesCall] = []

    def list_sources(self, *, search_text: str | None, page: int) -> SourceListing:
        self.calls.append(ListSourcesCall(search_text=search_text, page=page))
        return self._source_listing
