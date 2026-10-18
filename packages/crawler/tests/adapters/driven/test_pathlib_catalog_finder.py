"""``PathlibCatalogFinder``: a catalog on disk is found under its resolved path."""

from pathlib import Path, PurePath

import pytest

from p2pwatch.adapters.driven.pathlib_catalog_finder import PathlibCatalogFinder


def test_two_spellings_of_one_catalog_are_found_at_one_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.db").write_bytes(b"")
    (tmp_path / "link.db").symlink_to(tmp_path / "a.db")
    monkeypatch.chdir(tmp_path)

    found = [
        PathlibCatalogFinder().find_catalog(PurePath(spelling))
        for spelling in ("a.db", "./a.db", "link.db")
    ]

    assert found == [(tmp_path / "a.db").resolve()] * 3


def test_no_catalog_is_found_where_nothing_exists(tmp_path: Path) -> None:
    assert PathlibCatalogFinder().find_catalog(PurePath(tmp_path / "missing.db")) is None
