from collections.abc import Sequence
from pathlib import PurePath

from p2pwatch.application.ports.driven.catalog_copier import CatalogCopier
from p2pwatch.domain.catalog_copy_error import CatalogCopyError


class FakeCatalogCopier(CatalogCopier):
    """Records each copy, and raises ``failure`` when given one."""

    def __init__(self, failure: CatalogCopyError | None = None) -> None:
        self.copies: list[tuple[PurePath, list[PurePath], bool]] = []
        self._failure = failure

    def copy_catalogs(
        self,
        destination: PurePath,
        source_catalogs: Sequence[PurePath],
        *,
        destination_is_source: bool,
    ) -> None:
        self.copies.append((destination, list(source_catalogs), destination_is_source))
        if self._failure is not None:
            raise self._failure
