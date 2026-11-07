"""An exclusive opening: the database held from its first access until the connection closes."""

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Protocol

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.errors import HeldDatabaseError
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import open_catalog_at
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    database_opener,
    database_opener_held_at_reopen,
    open_catalog,
    open_reader,
)

_CATALOG_VERSION = database_opener().catalog_version()


class _HolderOpening(Protocol):
    def __call__(self, path: Path, /) -> sqlite3.Connection: ...


def _idle_reader(path: Path) -> sqlite3.Connection:
    reader = open_reader(path)
    try:
        reader.execute("SELECT count(*) FROM sqlite_schema").fetchone()
    except sqlite3.Error:
        reader.close()
        raise
    return reader


def _idle_writer_at_5(path: Path) -> sqlite3.Connection:
    return open_catalog_at(path, version=5)


def _version(path: Path) -> int:
    with closing(open_reader(path)) as connection:
        (row,) = rows(connection, sql="PRAGMA user_version")
        version: int = row["user_version"]
        return version


@pytest.mark.parametrize(
    "open_holder", [_idle_writer_at_5, _idle_reader], ids=["idle writer", "idle reader"]
)
def test_an_exclusive_opening_beside_another_connection_raises_held_database_error(
    *, tmp_path: Path, open_holder: _HolderOpening
) -> None:
    path = tmp_path / "catalog.db"
    open_catalog_at(path, version=5).close()
    with closing(open_holder(path)), pytest.raises(HeldDatabaseError) as refusal:
        database_opener().open_catalog(path, exclusive=True)

    assert str(refusal.value) == f"{path} is held by another connection"
    assert _version(path) == 5
    assert list(tmp_path.glob("*.pre-*")) == []


@pytest.mark.parametrize(
    "version", [_CATALOG_VERSION, 5], ids=["nothing pending", "reopened after a block"]
)
def test_an_exclusive_opening_holds_the_database_until_it_closes(
    *, tmp_path: Path, version: int
) -> None:
    path = tmp_path / "catalog.db"
    open_catalog_at(path, version=version).close()

    with (
        closing(database_opener().open_catalog(path, exclusive=True)),
        pytest.raises(sqlite3.OperationalError, match="database is locked"),
    ):
        _idle_reader(path)

    assert _version(path) == _CATALOG_VERSION


def test_a_database_held_alone_opens_in_wal_once_closed(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    database_opener().open_catalog(path, exclusive=True).close()

    with closing(open_catalog(path)) as connection:
        assert rows(connection, sql="PRAGMA journal_mode") == [{"journal_mode": "wal"}]


def test_a_reopen_that_finds_the_database_held_raises_it_migrated_its_copy_kept(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.db"
    open_catalog_at(path, version=5).close()
    holders: list[sqlite3.Connection] = []
    opener = database_opener_held_at_reopen(path, holders=holders)

    try:
        with pytest.raises(HeldDatabaseError, match="is held by another connection"):
            opener.open_catalog(path, exclusive=True)
    finally:
        for holder in holders:
            holder.close()

    assert len(holders) == 1
    assert _version(path) == _CATALOG_VERSION
    with closing(open_reader(path)) as connection:
        assert rows(connection, sql="PRAGMA quick_check") == [{"quick_check": "ok"}]
    assert [file.name.rpartition(".")[0] for file in tmp_path.glob("*.pre-*")] == [
        "catalog.db.pre-0006"
    ]
