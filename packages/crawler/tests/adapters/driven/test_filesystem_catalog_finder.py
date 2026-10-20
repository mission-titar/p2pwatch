"""``FilesystemCatalogFinder``: a catalog on disk is found under its resolved path."""

from pathlib import Path

from p2pwatch.adapters.driven.filesystem_catalog_finder import FilesystemCatalogFinder


def test_three_spellings_of_one_catalog_are_found_at_one_path(tmp_path: Path) -> None:
    (tmp_path / "a.db").write_bytes(b"")
    (tmp_path / "link.db").symlink_to(tmp_path / "a.db")
    (tmp_path / "sub").mkdir()

    found = [
        FilesystemCatalogFinder().find_catalog(spelling)
        for spelling in (tmp_path / "a.db", tmp_path / "sub" / ".." / "a.db", tmp_path / "link.db")
    ]

    assert found == [(tmp_path / "a.db").resolve()] * 3


def test_no_catalog_is_found_where_nothing_exists(tmp_path: Path) -> None:
    assert FilesystemCatalogFinder().find_catalog(tmp_path / "missing.db") is None
