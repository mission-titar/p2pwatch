"""``CatalogFinder`` over the filesystem: a catalog is whatever exists at the path."""

from pathlib import Path, PurePath

from p2pwatch.application.ports.driven.catalog_finder import CatalogFinder


class FilesystemCatalogFinder(CatalogFinder):
    """Resolves the path, absolute as the command line gives it, through its symbolic links."""

    def find_catalog(self, path: PurePath) -> PurePath | None:
        catalog = Path(path)
        return catalog.resolve() if catalog.exists() else None
