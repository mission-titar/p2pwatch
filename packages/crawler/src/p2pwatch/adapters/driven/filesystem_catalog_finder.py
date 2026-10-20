"""``CatalogFinder`` over the filesystem: a catalog is whatever exists at the path."""

from pathlib import Path, PurePath

from p2pwatch.ports.driven.catalog_finder import CatalogFinder


class FilesystemCatalogFinder(CatalogFinder):
    """Resolves the path through its symbolic links, relative to the directory ``cwd``."""

    def __init__(self, cwd: Path) -> None:
        self._cwd = cwd

    def find_catalog(self, path: PurePath) -> PurePath | None:
        catalog = self._cwd / path
        return catalog.resolve() if catalog.exists() else None
