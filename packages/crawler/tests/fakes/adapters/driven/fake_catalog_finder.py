from pathlib import PurePath

from p2pwatch.application.ports.driven.catalog_finder import CatalogFinder
from p2pwatch.domain.inaccessible_path_error import InaccessiblePathError


class FakeCatalogFinder(CatalogFinder):
    """Finds the catalogs of ``resolved_by_path``, each under its resolved path, and refuses to
    examine the paths of ``inaccessible``."""

    def __init__(
        self,
        resolved_by_path: dict[PurePath, PurePath],
        *,
        inaccessible: frozenset[PurePath] = frozenset(),
    ) -> None:
        self._resolved_by_path = resolved_by_path
        self._inaccessible = inaccessible

    def find_catalog(self, path: PurePath) -> PurePath | None:
        if path in self._inaccessible:
            raise InaccessiblePathError(f"cannot examine {path}")
        return self._resolved_by_path.get(path)
