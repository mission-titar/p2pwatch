"""Lists the catalog's files a page at a time, with the counts the files page shows."""

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.application.ports.driven.catalog_file_reader import CatalogFileReader
from p2pwatch.application.ports.driving.file_lister import FileLister, FileListing
from p2pwatch.application.use_cases.paging import PAGE_SIZE
from p2pwatch.domain.catalog_entry import CatalogEntrySort, SortDirection


class ListFiles(FileLister):
    def __init__(self, catalog_file_reader: CatalogFileReader) -> None:
        self._catalog_file_reader = catalog_file_reader

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
        reader = self._catalog_file_reader
        catalog_entries = reader.read_catalog_entries(
            target_id=target_id,
            tier=tier,
            search_text=search_text,
            matched_only=matched_only,
            sort=sort,
            direction=direction,
            limit=PAGE_SIZE,
            offset=(page - 1) * PAGE_SIZE,
        )
        matched_file_count, total_file_count = reader.read_matched_and_total_file_counts(
            target_id=target_id, tier=tier, search_text=search_text
        )
        return FileListing(
            catalog_entries=catalog_entries,
            # A full page offers the next one, even when it turns out empty.
            has_next_page=len(catalog_entries) >= PAGE_SIZE,
            matched_file_count=matched_file_count,
            total_file_count=total_file_count,
            file_count_by_tier=reader.read_file_count_by_tier(
                target_id=target_id, search_text=search_text
            ),
        )
