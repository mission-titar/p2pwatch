"""``FileLister``: lists the catalog's files, for the files page and a target's page."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.domain.catalog_entry import CatalogEntry, CatalogEntrySort, SortDirection


@dataclass(kw_only=True, frozen=True)
class FileListing:
    catalog_entries: tuple[CatalogEntry, ...]  # the page asked for
    has_next_page: bool  # the page is full, so the next one may hold more
    matched_file_count: int  # without ``matched_only``, as the two counts below
    total_file_count: int
    file_count_by_tier: Mapping[DecisionTier, int]  # without the ``tier`` filter


class FileLister(ABC):
    """Lists the catalog's files, from any thread."""

    @abstractmethod
    def list_files(
        self,
        *,
        target_id: TargetId | None,
        tier: DecisionTier | None,
        search_text: str | None,
        matched_only: bool,
        sort: CatalogEntrySort,
        direction: SortDirection,
        page: int,
    ) -> FileListing:
        """The ``page``-th page (from 1) of the files passing the filters, and their counts."""
