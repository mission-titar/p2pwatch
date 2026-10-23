from dataclasses import dataclass

from catalog_matching.domain.decision_tier import DecisionTier
from p2pwatch.application.ports.driving.file_lister import FileLister, FileListing
from p2pwatch.domain.catalog_entry import CatalogEntrySort, SortDirection


@dataclass(frozen=True)
class ListFilesCall:
    """The arguments of one ``list_files`` call."""

    target_id: str | None
    tier: DecisionTier | None
    search_text: str | None
    matched_only: bool
    sort: CatalogEntrySort
    direction: SortDirection
    page: int


class FakeFileLister(FileLister):
    """Lists the files it is given, and keeps each call's arguments."""

    def __init__(self, file_listing: FileListing) -> None:
        self._file_listing = file_listing
        self.calls: list[ListFilesCall] = []

    def list_files(
        self,
        *,
        target_id: str | None,
        tier: DecisionTier | None,
        search_text: str | None,
        matched_only: bool,
        sort: CatalogEntrySort,
        direction: SortDirection,
        page: int,
    ) -> FileListing:
        call = ListFilesCall(target_id, tier, search_text, matched_only, sort, direction, page)
        self.calls.append(call)
        return self._file_listing
