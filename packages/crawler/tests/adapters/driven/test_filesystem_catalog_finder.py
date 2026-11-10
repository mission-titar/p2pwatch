"""``FilesystemCatalogFinder``: a catalog on disk is found under its resolved path."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.filesystem_catalog_finder import FilesystemCatalogFinder
from p2pwatch.domain.inaccessible_path_error import InaccessiblePathError
from tests.contracts.application.ports.driven.catalog_finder_contract import (
    CatalogFinderContract,
)

_UNSEARCHABLE = pytest.param(
    "unsearchable",
    marks=pytest.mark.skipif(os.geteuid() == 0, reason="root searches every directory"),
)


class TestFilesystemCatalogFinder(CatalogFinderContract):
    @pytest.fixture
    def catalog_finder(self) -> FilesystemCatalogFinder:
        return FilesystemCatalogFinder()

    @pytest.fixture
    def catalog(self, tmp_path: Path) -> Path:
        (tmp_path / "catalog.db").write_bytes(b"")
        return tmp_path / "catalog.db"

    @pytest.fixture(params=["nothing", "under a file"])
    def missing_catalog(self, *, request: pytest.FixtureRequest, tmp_path: Path) -> Path:
        if request.param == "nothing":
            return tmp_path / "missing.db"
        (tmp_path / "file").write_bytes(b"")
        return tmp_path / "file" / "catalog.db"

    @pytest.fixture(params=["name too long", _UNSEARCHABLE])
    def inaccessible_catalog(
        self, *, request: pytest.FixtureRequest, tmp_path: Path
    ) -> Iterator[Path]:
        """A real refusal of ``stat``: a name past the filesystem's bound, or a catalog past a
        directory it cannot search."""
        if request.param == "name too long":
            yield tmp_path / ("c" * 256)
            return
        locked = tmp_path / "locked"
        locked.mkdir()
        (locked / "catalog.db").write_bytes(b"")
        locked.chmod(0)
        yield locked / "catalog.db"
        locked.chmod(0o700)


def test_three_spellings_of_one_catalog_are_found_at_one_path(tmp_path: Path) -> None:
    (tmp_path / "a.db").write_bytes(b"")
    (tmp_path / "link.db").symlink_to(tmp_path / "a.db")
    (tmp_path / "sub").mkdir()

    found = [
        FilesystemCatalogFinder().find_catalog(spelling)
        for spelling in (tmp_path / "a.db", tmp_path / "sub" / ".." / "a.db", tmp_path / "link.db")
    ]

    assert found == [(tmp_path / "a.db").resolve()] * 3


def test_the_refusal_names_the_path_and_chains_the_system_s_error(tmp_path: Path) -> None:
    too_long = tmp_path / ("c" * 256)
    with pytest.raises(InaccessiblePathError) as refusal:
        FilesystemCatalogFinder().find_catalog(too_long)
    assert str(refusal.value) == (f"cannot examine {too_long}: File name too long")
    assert isinstance(refusal.value.__cause__, OSError)
