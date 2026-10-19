"""``CatalogFileReader``: reads the catalog's files."""

from abc import ABC, abstractmethod
from collections.abc import Mapping


class CatalogFileReader(ABC):
    """Reads the catalog from any thread. A file passes ``target_id`` when it holds a current
    decision of that target and a tier other than ``catalog``, ``tier`` when it holds one of that
    tier, ``search_text`` when its latest filename contains it."""

    @abstractmethod
    def read_matched_and_total_file_counts(
        self, *, target_id: str | None, tier: str | None, search_text: str | None
    ) -> tuple[int, int]:
        """Of the files passing the filters, how many hold a current decision, and how many in
        all."""

    @abstractmethod
    def read_file_count_by_tier(
        self, *, target_id: str | None, search_text: str | None
    ) -> Mapping[str, int]:
        """By tier, how many files passing the filters hold a current decision of that tier."""
