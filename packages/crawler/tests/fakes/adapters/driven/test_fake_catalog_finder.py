from pathlib import PurePath

import pytest

from tests.contracts.application.ports.driven.catalog_finder_contract import (
    CatalogFinderContract,
)
from tests.fakes.adapters.driven.fake_catalog_finder import FakeCatalogFinder


class TestFakeCatalogFinder(CatalogFinderContract):
    @pytest.fixture
    def catalog_finder(
        self, *, catalog: PurePath, inaccessible_catalog: PurePath
    ) -> FakeCatalogFinder:
        return FakeCatalogFinder(
            {catalog: PurePath("/resolved/catalog.db")},
            inaccessible=frozenset({inaccessible_catalog}),
        )

    @pytest.fixture
    def catalog(self) -> PurePath:
        return PurePath("/catalogs/catalog.db")

    @pytest.fixture
    def missing_catalog(self) -> PurePath:
        return PurePath("/catalogs/missing.db")

    @pytest.fixture
    def inaccessible_catalog(self) -> PurePath:
        return PurePath("/catalogs/inaccessible.db")
