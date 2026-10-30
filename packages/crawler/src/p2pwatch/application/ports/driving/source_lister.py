"""``SourceLister``: lists the catalog's sources, for the sources page."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from p2pwatch.domain.known_source import KnownSource


@dataclass(kw_only=True, frozen=True)
class SourceListing:
    known_sources: tuple[KnownSource, ...]  # the page asked for
    has_next_page: bool  # the page is full, so the next one may hold more
    source_count: int  # every source passing the search, on every page


class SourceLister(ABC):
    """Lists the catalog's sources, from any thread."""

    @abstractmethod
    def list_sources(self, *, search_text: str | None, page: int) -> SourceListing:
        """The ``page``-th page (from 1) of the sources passing the search, and their count."""
