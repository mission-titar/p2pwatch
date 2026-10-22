"""Merges catalogs, refusing first any merge that could lose a catalog."""

from collections.abc import Sequence
from pathlib import PurePath
from typing import assert_never

from p2pwatch.application.ports.driven.catalog_copier import CatalogCopier
from p2pwatch.application.ports.driven.catalog_finder import CatalogFinder
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driving.catalog_merger import (
    CatalogMerger,
    ListedSourceCatalog,
    NewCatalog,
)
from p2pwatch.domain.catalog_copy_error import CatalogCopyError
from p2pwatch.domain.merge_error import MergeError


class MergeCatalogs(CatalogMerger):
    """Sources must exist; a new catalog must not, unless forced; a listed one must be a source."""

    def __init__(
        self, catalog_finder: CatalogFinder, catalog_copier: CatalogCopier, logger: Logger
    ) -> None:
        self._catalog_finder = catalog_finder
        self._catalog_copier = catalog_copier
        self._logger = logger

    def merge_catalogs(
        self, source_catalogs: Sequence[PurePath], destination: NewCatalog | ListedSourceCatalog
    ) -> None:
        found_sources = [self._find_source(source_catalog) for source_catalog in source_catalogs]
        match destination:
            case NewCatalog(path=path, force=force):
                if not force and self._catalog_finder.find_catalog(path) is not None:
                    raise MergeError(
                        f"destination already exists: {path} (force the merge to append to it)"
                    )
                destination_is_source = False
            case ListedSourceCatalog(path=path):
                if self._catalog_finder.find_catalog(path) not in found_sources:
                    raise MergeError(f"destination must be one of the source catalogs: {path}")
                destination_is_source = True
            case _:  # pragma: no cover
                assert_never(destination)
        self._logger.info("merge → %s (%d source catalog(s))", path, len(source_catalogs))
        try:
            self._catalog_copier.copy_catalogs(
                path, source_catalogs, destination_is_source=destination_is_source
            )
        except CatalogCopyError as error:
            raise MergeError(str(error)) from error
        self._logger.info("merge done: %s", path)

    def _find_source(self, source_catalog: PurePath) -> PurePath:
        found_source = self._catalog_finder.find_catalog(source_catalog)
        if found_source is None:
            raise MergeError(f"source catalog not found: {source_catalog}")
        return found_source
