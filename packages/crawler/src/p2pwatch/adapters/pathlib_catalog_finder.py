"""``CatalogFinder`` over ``pathlib``: a catalog is whatever exists at the path."""

from pathlib import Path, PurePath

from p2pwatch.ports.driven.catalog_finder import CatalogFinder


class PathlibCatalogFinder(CatalogFinder):
    """Resolves the path through its symbolic links, relative to the working directory."""

    def find_catalog(self, path: PurePath) -> PurePath | None:
        catalog = Path(path)
        return catalog.resolve() if catalog.exists() else None
