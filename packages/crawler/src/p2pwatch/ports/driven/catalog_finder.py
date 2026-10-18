"""``CatalogFinder``: tells whether a catalog exists at a path, and where it really is."""

from abc import ABC, abstractmethod
from pathlib import PurePath


class CatalogFinder(ABC):
    """Finds a catalog by its path, so that two spellings of one file compare equal."""

    @abstractmethod
    def find_catalog(self, path: PurePath) -> PurePath | None:
        """The catalog's resolved path, or ``None`` when there is no catalog at ``path``."""
