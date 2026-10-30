"""``MergeCatalogs``: refuses a merge that could lose a catalog, then copies the sources."""

from pathlib import PurePath

import pytest

from p2pwatch.application.ports.driving.catalog_merger import ListedSourceCatalog, NewCatalog
from p2pwatch.application.use_cases.merge_catalogs import MergeCatalogs
from p2pwatch.domain.catalog_copy_error import CatalogCopyError
from p2pwatch.domain.merge_error import MergeError, OutputIsSourceError
from tests.fakes.adapters.driven.fake_catalog_copier import FakeCatalogCopier
from tests.fakes.adapters.driven.fake_catalog_finder import FakeCatalogFinder
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine

_A = PurePath("a.db")
_B = PurePath("b.db")
_OUT = PurePath("out.db")


_SOURCES_RESOLVED = {_A: PurePath("/data/a.db"), _B: PurePath("/data/b.db")}


def _sources_found() -> FakeCatalogFinder:
    return FakeCatalogFinder(_SOURCES_RESOLVED)


def test_a_new_catalog_receives_every_source() -> None:
    catalog_copier = FakeCatalogCopier()

    MergeCatalogs(
        _sources_found(), catalog_copier=catalog_copier, logger=FakeLogger()
    ).merge_catalogs([_A, _B], destination=NewCatalog(path=_OUT, force=False))

    assert catalog_copier.copies == [(_OUT, [_A, _B])]


def test_a_missing_source_is_refused_before_anything_is_copied() -> None:
    catalog_copier = FakeCatalogCopier()
    missing = PurePath("missing.db")

    with pytest.raises(MergeError, match=f"^source catalog not found: {missing}$"):
        MergeCatalogs(
            _sources_found(), catalog_copier=catalog_copier, logger=FakeLogger()
        ).merge_catalogs([_A, missing], destination=NewCatalog(path=_OUT, force=False))

    assert catalog_copier.copies == []


def test_a_new_catalog_that_exists_is_refused_unless_forced() -> None:
    catalog_finder = FakeCatalogFinder({_A: _A, _OUT: _OUT})
    catalog_copier = FakeCatalogCopier()

    with pytest.raises(MergeError, match=f"^destination already exists: {_OUT} "):
        MergeCatalogs(
            catalog_finder, catalog_copier=catalog_copier, logger=FakeLogger()
        ).merge_catalogs([_A], destination=NewCatalog(path=_OUT, force=False))

    assert catalog_copier.copies == []


def test_a_forced_merge_appends_to_the_existing_catalog() -> None:
    catalog_copier = FakeCatalogCopier()

    MergeCatalogs(
        FakeCatalogFinder({_A: _A, _OUT: _OUT}), catalog_copier=catalog_copier, logger=FakeLogger()
    ).merge_catalogs([_A], destination=NewCatalog(path=_OUT, force=True))

    assert catalog_copier.copies == [(_OUT, [_A])]


def test_a_listed_source_receives_the_others_under_any_spelling() -> None:
    spelled_otherwise = PurePath("./a.db")
    catalog_finder = FakeCatalogFinder(
        {**_SOURCES_RESOLVED, spelled_otherwise: PurePath("/data/a.db")}
    )
    catalog_copier = FakeCatalogCopier()

    MergeCatalogs(
        catalog_finder, catalog_copier=catalog_copier, logger=FakeLogger()
    ).merge_catalogs([_A, _B], destination=ListedSourceCatalog(path=spelled_otherwise))

    assert catalog_copier.copies == [(spelled_otherwise, [_B])]


@pytest.mark.parametrize("force", [False, True])
def test_an_output_that_is_also_a_source_is_refused_forced_or_not(force: bool) -> None:
    spelled_otherwise = PurePath("./a.db")
    catalog_finder = FakeCatalogFinder(
        {**_SOURCES_RESOLVED, spelled_otherwise: PurePath("/data/a.db")}
    )
    catalog_copier = FakeCatalogCopier()

    with pytest.raises(OutputIsSourceError) as raised:
        MergeCatalogs(
            catalog_finder, catalog_copier=catalog_copier, logger=FakeLogger()
        ).merge_catalogs([_A, _B], destination=NewCatalog(path=spelled_otherwise, force=force))

    assert raised.value.output == spelled_otherwise
    assert catalog_copier.copies == []


def test_a_destination_that_is_not_a_listed_source_is_refused() -> None:
    other = PurePath("other.db")
    catalog_finder = FakeCatalogFinder({**_SOURCES_RESOLVED, other: PurePath("/data/other.db")})
    catalog_copier = FakeCatalogCopier()

    with pytest.raises(
        MergeError, match=f"^destination must be one of the source catalogs: {other}$"
    ):
        MergeCatalogs(
            catalog_finder, catalog_copier=catalog_copier, logger=FakeLogger()
        ).merge_catalogs([_A, _B], destination=ListedSourceCatalog(path=other))

    assert catalog_copier.copies == []


def test_a_failed_copy_is_a_merge_error_chained_to_it() -> None:
    copy_error = CatalogCopyError("copy of b.db failed: no such table")

    with pytest.raises(MergeError, match="^copy of b.db failed: no such table$") as raised:
        MergeCatalogs(
            _sources_found(), catalog_copier=FakeCatalogCopier(copy_error), logger=FakeLogger()
        ).merge_catalogs([_A, _B], destination=NewCatalog(path=_OUT, force=False))

    assert raised.value.__cause__ is copy_error


def test_the_merge_logs_its_destination_before_and_after_the_copy() -> None:
    logger = FakeLogger()

    MergeCatalogs(
        _sources_found(), catalog_copier=FakeCatalogCopier(), logger=logger
    ).merge_catalogs([_A, _B], destination=NewCatalog(path=_OUT, force=False))

    assert logger.lines == [
        LoggedLine(level="info", message=f"merge → {_OUT} (2 source catalog(s))"),
        LoggedLine(level="info", message=f"merge done: {_OUT}"),
    ]


def test_a_listed_source_is_logged_as_skipped_before_the_copy() -> None:
    logger = FakeLogger()

    MergeCatalogs(
        _sources_found(), catalog_copier=FakeCatalogCopier(), logger=logger
    ).merge_catalogs([_A, _B], destination=ListedSourceCatalog(path=_A))

    assert logger.lines == [
        LoggedLine(level="info", message=f"merge → {_A} (2 source catalog(s))"),
        LoggedLine(level="info", message=f"{_A} skipped: it is the output"),
        LoggedLine(level="info", message=f"merge done: {_A}"),
    ]
