from pathlib import PurePath

from p2pwatch.application.ports.driven.catalog_finder import CatalogFinder


class FakeCatalogFinder(CatalogFinder):
    """Finds the catalogs of ``resolved_by_path``, each under its resolved path."""

    def __init__(self, resolved_by_path: dict[PurePath, PurePath]) -> None:
        self._resolved_by_path = resolved_by_path

    def find_catalog(self, path: PurePath) -> PurePath | None:
        return self._resolved_by_path.get(path)
