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
from p2pwatch.domain.catalog_copy_error import CatalogCopyError, PartialCopyError
from p2pwatch.domain.merge_error import MergeError, OutputIsSourceError, PartialMergeError


class MergeCatalogs(CatalogMerger):
    """Sources must exist; a new catalog must be no source, nor exist unless forced; a listed one
    must be a source, which receives the others."""

    def __init__(
        self, catalog_finder: CatalogFinder, *, catalog_copier: CatalogCopier, logger: Logger
    ) -> None:
        self._catalog_finder = catalog_finder
        self._catalog_copier = catalog_copier
        self._logger = logger

    def merge_catalogs(
        self, source_catalogs: Sequence[PurePath], *, destination: NewCatalog | ListedSourceCatalog
    ) -> None:
        found_sources = [self._find_source(source_catalog) for source_catalog in source_catalogs]
        found_destination = self._catalog_finder.find_catalog(destination.path)
        match destination:
            case NewCatalog(path=path, force=force):
                if found_destination in found_sources:
                    raise OutputIsSourceError(path)
                if not force and found_destination is not None:
                    raise MergeError(
                        f"destination already exists: {path} (force the merge to append to it)"
                    )
            case ListedSourceCatalog(path=path):
                if found_destination not in found_sources:
                    raise MergeError(f"destination must be one of the source catalogs: {path}")
            case _:  # pragma: no cover
                assert_never(destination)
        self._logger.info("merge → %s (%d source catalog(s))", path, len(source_catalogs))
        catalogs_to_copy = []
        for source_catalog, found_source in zip(source_catalogs, found_sources, strict=True):
            if found_source == found_destination:
                self._logger.info("%s skipped: it is the output", source_catalog)
            else:
                catalogs_to_copy.append(source_catalog)
        try:
            self._catalog_copier.copy_catalogs(path, source_catalogs=catalogs_to_copy)
        except PartialCopyError as error:
            raise PartialMergeError(str(error)) from error
        except CatalogCopyError as error:
            raise MergeError(str(error)) from error
        self._logger.info("merge done: %s", path)

    def _find_source(self, source_catalog: PurePath) -> PurePath:
        found_source = self._catalog_finder.find_catalog(source_catalog)
        if found_source is None:
            raise MergeError(f"source catalog not found: {source_catalog}")
        return found_source
