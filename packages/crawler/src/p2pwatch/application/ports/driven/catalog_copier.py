"""``CatalogCopier``: copies the rows of catalogs into another, idempotent."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import PurePath


class CatalogCopier(ABC):
    """Copies every row a destination lacks, never writing to a source."""

    @abstractmethod
    def copy_catalogs(self, destination: PurePath, *, source_catalogs: Sequence[PurePath]) -> None:
        """Copies each source whole into ``destination`` once all are checked; raises
        ``CatalogCopyError`` before any write, or ``PartialCopyError``, the sources before kept."""
