"""``CatalogFinder`` over the filesystem: a catalog is whatever exists at the path."""

from pathlib import Path, PurePath

from p2pwatch.application.ports.driven.catalog_finder import CatalogFinder
from p2pwatch.domain.inaccessible_path_error import InaccessiblePathError


class FilesystemCatalogFinder(CatalogFinder):
    """Resolves the path, absolute as the command line gives it, through its symbolic links."""

    def find_catalog(self, path: PurePath) -> PurePath | None:
        catalog = Path(path)
        try:
            exists = catalog.exists()
        except OSError as error:
            raise InaccessiblePathError(f"cannot examine {path}: {error}") from error
        return catalog.resolve() if exists else None
