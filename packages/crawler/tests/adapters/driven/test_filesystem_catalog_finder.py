"""``FilesystemCatalogFinder``: a catalog on disk is found under its resolved path."""

from pathlib import Path, PurePath

from p2pwatch.adapters.driven.filesystem_catalog_finder import FilesystemCatalogFinder


def test_two_spellings_of_one_catalog_are_found_at_one_path_under_the_directory_given(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.db").write_bytes(b"")
    (tmp_path / "link.db").symlink_to(tmp_path / "a.db")

    found = [
        FilesystemCatalogFinder(tmp_path).find_catalog(PurePath(spelling))
        for spelling in ("a.db", "./a.db", "link.db")
    ]

    assert found == [(tmp_path / "a.db").resolve()] * 3


def test_an_absolute_path_is_found_wherever_the_directory_given(tmp_path: Path) -> None:
    (tmp_path / "a.db").write_bytes(b"")
    (tmp_path / "elsewhere").mkdir()

    found = FilesystemCatalogFinder(tmp_path / "elsewhere").find_catalog(tmp_path / "a.db")

    assert found == (tmp_path / "a.db").resolve()


def test_no_catalog_is_found_where_nothing_exists(tmp_path: Path) -> None:
    assert FilesystemCatalogFinder(tmp_path).find_catalog(PurePath("missing.db")) is None
