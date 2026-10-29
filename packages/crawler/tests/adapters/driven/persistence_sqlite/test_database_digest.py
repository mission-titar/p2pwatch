import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.database_digest import database_digest
from p2pwatch.adapters.driven.persistence_sqlite.named_row import named_row

_ROWS = [(1, "a"), (2, "b"), (3, None), (4, b"\x00")]


@pytest.fixture
def database(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Two tables of the same shape, ``a`` holding the rows, ``b`` empty, and an AUTOINCREMENT
    table that fills ``sqlite_sequence``."""
    with closing(sqlite3.connect(tmp_path / "digest.db", autocommit=True)) as connection:
        connection.executescript(
            "PRAGMA user_version = 3;"
            "CREATE TABLE a (x INTEGER, y);"
            "CREATE TABLE b (x INTEGER, y);"
            "CREATE TABLE c (id INTEGER PRIMARY KEY AUTOINCREMENT);"
            "INSERT INTO c DEFAULT VALUES;"
        )
        connection.executemany("INSERT INTO a VALUES (?, ?)", _ROWS)
        yield connection


def test_a_vacuum_into_copy_has_the_same_digest(
    database: sqlite3.Connection, tmp_path: Path
) -> None:
    copy_path = tmp_path / "copy.db"
    database.execute("VACUUM INTO ?", (str(copy_path),))
    with closing(sqlite3.connect(copy_path)) as copy:
        assert database_digest(copy) == database_digest(database)


def test_the_same_rows_inserted_in_another_order_have_the_same_digest(
    database: sqlite3.Connection, tmp_path: Path
) -> None:
    with closing(sqlite3.connect(tmp_path / "reversed.db", autocommit=True)) as reversed_rows:
        reversed_rows.executescript(
            "PRAGMA user_version = 3;"
            "CREATE TABLE a (x INTEGER, y);"
            "CREATE TABLE b (x INTEGER, y);"
            "CREATE TABLE c (id INTEGER PRIMARY KEY AUTOINCREMENT);"
            "INSERT INTO c DEFAULT VALUES;"
        )
        reversed_rows.executemany("INSERT INTO a VALUES (?, ?)", reversed(_ROWS))
        assert database_digest(reversed_rows) == database_digest(database)


def test_a_connection_carrying_the_row_factory_has_the_digest_of_a_raw_one(
    database: sqlite3.Connection,
) -> None:
    before = database_digest(database)
    database.row_factory = named_row
    assert database_digest(database) == before


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE a SET y = 'z' WHERE x = 1",
        "UPDATE a SET y = CAST(y AS BLOB) WHERE x = 1",
        "INSERT INTO b SELECT * FROM a WHERE x = 1; DELETE FROM a WHERE x = 1",
        "INSERT INTO c DEFAULT VALUES; DELETE FROM c WHERE id = 2",
        "CREATE INDEX a_x ON a (x)",
        "PRAGMA user_version = 4",
    ],
    ids=["a row", "a value's type", "a row's table", "sqlite_sequence", "the schema", "version"],
)
def test_a_change_changes_the_digest(database: sqlite3.Connection, change: str) -> None:
    before = database_digest(database)
    database.executescript(change)
    assert database_digest(database) != before
