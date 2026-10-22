"""``MergeCatalogs``: refuses a merge that could lose a catalog, then copies the sources."""

from collections.abc import Sequence
from pathlib import PurePath

import pytest

from p2pwatch.application.ports.driven.catalog_copier import CatalogCopier
from p2pwatch.application.ports.driven.catalog_finder import CatalogFinder
from p2pwatch.application.ports.driving.catalog_merger import ListedSourceCatalog, NewCatalog
from p2pwatch.application.use_cases.merge_catalogs import MergeCatalogs
from p2pwatch.domain.catalog_copy_error import CatalogCopyError
from p2pwatch.domain.merge_error import MergeError
from tests.fakes.application.fakes import FakeLogger, LoggedLine

_A = PurePath("a.db")
_B = PurePath("b.db")
_OUT = PurePath("out.db")


class _FakeCatalogFinder(CatalogFinder):
    """Finds the catalogs of ``resolved_by_path``, each under its resolved path."""

    def __init__(self, resolved_by_path: dict[PurePath, PurePath]) -> None:
        self._resolved_by_path = resolved_by_path

    def find_catalog(self, path: PurePath) -> PurePath | None:
        return self._resolved_by_path.get(path)


class _FakeCatalogCopier(CatalogCopier):
    """Records each copy, and raises ``failure`` when given one."""

    def __init__(self, failure: CatalogCopyError | None = None) -> None:
        self.copies: list[tuple[PurePath, list[PurePath], bool]] = []
        self._failure = failure

    def copy_catalogs(
        self,
        destination: PurePath,
        source_catalogs: Sequence[PurePath],
        *,
        destination_is_source: bool,
    ) -> None:
        self.copies.append((destination, list(source_catalogs), destination_is_source))
        if self._failure is not None:
            raise self._failure


_SOURCES_RESOLVED = {_A: PurePath("/data/a.db"), _B: PurePath("/data/b.db")}


def _sources_found() -> _FakeCatalogFinder:
    return _FakeCatalogFinder(_SOURCES_RESOLVED)


def test_a_new_catalog_receives_every_source() -> None:
    catalog_copier = _FakeCatalogCopier()

    MergeCatalogs(_sources_found(), catalog_copier, FakeLogger()).merge_catalogs(
        [_A, _B], NewCatalog(_OUT, force=False)
    )

    assert catalog_copier.copies == [(_OUT, [_A, _B], False)]


def test_a_missing_source_is_refused_before_anything_is_copied() -> None:
    catalog_copier = _FakeCatalogCopier()
    missing = PurePath("missing.db")

    with pytest.raises(MergeError, match=f"^source catalog not found: {missing}$"):
        MergeCatalogs(_sources_found(), catalog_copier, FakeLogger()).merge_catalogs(
            [_A, missing], NewCatalog(_OUT, force=False)
        )

    assert catalog_copier.copies == []


def test_a_new_catalog_that_exists_is_refused_unless_forced() -> None:
    catalog_finder = _FakeCatalogFinder({_A: _A, _OUT: _OUT})
    catalog_copier = _FakeCatalogCopier()

    with pytest.raises(MergeError, match=f"^destination already exists: {_OUT} "):
        MergeCatalogs(catalog_finder, catalog_copier, FakeLogger()).merge_catalogs(
            [_A], NewCatalog(_OUT, force=False)
        )

    assert catalog_copier.copies == []


def test_a_forced_merge_appends_to_the_existing_catalog() -> None:
    catalog_copier = _FakeCatalogCopier()

    MergeCatalogs(
        _FakeCatalogFinder({_A: _A, _OUT: _OUT}), catalog_copier, FakeLogger()
    ).merge_catalogs([_A], NewCatalog(_OUT, force=True))

    assert catalog_copier.copies == [(_OUT, [_A], False)]


def test_a_listed_source_receives_the_others_under_any_spelling() -> None:
    spelled_otherwise = PurePath("./a.db")
    catalog_finder = _FakeCatalogFinder(
        {**_SOURCES_RESOLVED, spelled_otherwise: PurePath("/data/a.db")}
    )
    catalog_copier = _FakeCatalogCopier()

    MergeCatalogs(catalog_finder, catalog_copier, FakeLogger()).merge_catalogs(
        [_A, _B], ListedSourceCatalog(spelled_otherwise)
    )

    assert catalog_copier.copies == [(spelled_otherwise, [_A, _B], True)]


def test_a_destination_that_is_not_a_listed_source_is_refused() -> None:
    other = PurePath("other.db")
    catalog_finder = _FakeCatalogFinder({**_SOURCES_RESOLVED, other: PurePath("/data/other.db")})
    catalog_copier = _FakeCatalogCopier()

    with pytest.raises(
        MergeError, match=f"^destination must be one of the source catalogs: {other}$"
    ):
        MergeCatalogs(catalog_finder, catalog_copier, FakeLogger()).merge_catalogs(
            [_A, _B], ListedSourceCatalog(other)
        )

    assert catalog_copier.copies == []


def test_a_failed_copy_is_a_merge_error_chained_to_it() -> None:
    copy_error = CatalogCopyError("copy of b.db failed: no such table")

    with pytest.raises(MergeError, match="^copy of b.db failed: no such table$") as raised:
        MergeCatalogs(
            _sources_found(), _FakeCatalogCopier(copy_error), FakeLogger()
        ).merge_catalogs([_A, _B], NewCatalog(_OUT, force=False))

    assert raised.value.__cause__ is copy_error


def test_the_merge_logs_its_destination_before_and_after_the_copy() -> None:
    logger = FakeLogger()

    MergeCatalogs(_sources_found(), _FakeCatalogCopier(), logger).merge_catalogs(
        [_A, _B], NewCatalog(_OUT, force=False)
    )

    assert logger.lines == [
        LoggedLine("info", f"merge → {_OUT} (2 source catalog(s))"),
        LoggedLine("info", f"merge done: {_OUT}"),
    ]
