from collections.abc import Sequence
from pathlib import PurePath

from p2pwatch.application.ports.driving.catalog_merger import (
    CatalogMerger,
    ListedSourceCatalog,
    NewCatalog,
)
from p2pwatch.domain.merge_error import MergeError


class FakeCatalogMerger(CatalogMerger):
    """Records each merge, and raises ``refusal`` when given one."""

    def __init__(self, refusal: MergeError | None = None) -> None:
        self.merges: list[tuple[list[PurePath], NewCatalog | ListedSourceCatalog]] = []
        self._refusal = refusal

    def merge_catalogs(
        self, source_catalogs: Sequence[PurePath], *, destination: NewCatalog | ListedSourceCatalog
    ) -> None:
        self.merges.append((list(source_catalogs), destination))
        if self._refusal is not None:
            raise self._refusal
