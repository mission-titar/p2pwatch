"""``CatalogMerger``: merges catalogs into a new one or into one of them, idempotent."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePath


class MergeError(Exception):
    """A merge refused before copying, or a copy that failed: each source is copied whole or not."""


@dataclass(frozen=True)
class NewCatalog:
    """A destination outside the sources, refused if it exists unless ``force``."""

    path: PurePath
    force: bool


@dataclass(frozen=True)
class ListedSourceCatalog:
    """A destination that is one of the sources: the others are merged into it."""

    path: PurePath


class CatalogMerger(ABC):
    """Merges catalogs without losing one: merging the same sources again adds nothing."""

    @abstractmethod
    def merge_catalogs(
        self, source_catalogs: Sequence[PurePath], destination: NewCatalog | ListedSourceCatalog
    ) -> None:
        """Returns once every source is in ``destination``; raises ``MergeError`` otherwise."""
