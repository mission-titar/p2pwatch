"""The promise of the ``CatalogFinder`` port."""

from abc import ABC, abstractmethod
from pathlib import PurePath

import pytest

from p2pwatch.application.ports.driven.catalog_finder import CatalogFinder
from p2pwatch.domain.inaccessible_path_error import InaccessiblePathError


class CatalogFinderContract(ABC):
    @pytest.fixture
    @abstractmethod
    def catalog_finder(self) -> CatalogFinder:
        """The finder under test."""

    @pytest.fixture
    @abstractmethod
    def catalog(self) -> PurePath:
        """The path of a catalog ``catalog_finder`` finds."""

    @pytest.fixture
    @abstractmethod
    def missing_catalog(self) -> PurePath:
        """A path where no catalog is."""

    @pytest.fixture
    @abstractmethod
    def inaccessible_catalog(self) -> PurePath:
        """A path the filesystem refuses to examine."""

    def test_a_catalog_is_found_at_one_path_each_time(
        self, *, catalog_finder: CatalogFinder, catalog: PurePath
    ) -> None:
        found = catalog_finder.find_catalog(catalog)
        assert found is not None
        assert catalog_finder.find_catalog(catalog) == found

    def test_no_catalog_is_found_where_none_is(
        self, *, catalog_finder: CatalogFinder, missing_catalog: PurePath
    ) -> None:
        assert catalog_finder.find_catalog(missing_catalog) is None

    def test_a_path_it_cannot_examine_raises_inaccessible_path_error(
        self, *, catalog_finder: CatalogFinder, inaccessible_catalog: PurePath
    ) -> None:
        with pytest.raises(InaccessiblePathError):
            catalog_finder.find_catalog(inaccessible_catalog)
