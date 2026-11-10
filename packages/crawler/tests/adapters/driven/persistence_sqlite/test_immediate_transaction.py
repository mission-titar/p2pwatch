import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.immediate_transaction import (
    immediate_transaction,
)
from tests.support.adapters.driven.persistence_sqlite.named_row import rows

# Past a page's free space, so that the write needs a new page.
_LONG_VALUE = "x" * 65_536


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(tmp_path / "database.db", autocommit=True)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("CREATE TABLE parents (id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE children (id INTEGER PRIMARY KEY, parent_id INTEGER"
            " REFERENCES parents (id) DEFERRABLE INITIALLY DEFERRED, value TEXT)"
        )
        yield connection


def _child_count(connection: sqlite3.Connection) -> int:
    [row] = rows(connection, sql="SELECT count(*) AS child_count FROM children")
    child_count: int = row["child_count"]
    return child_count


def test_a_block_that_ends_commits_its_writes(connection: sqlite3.Connection) -> None:
    with immediate_transaction(connection):
        assert connection.in_transaction
        connection.execute("INSERT INTO children (id) VALUES (1)")
    assert not connection.in_transaction
    assert _child_count(connection) == 1


def test_a_block_that_raises_rolls_back_and_the_exception_propagates(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(KeyboardInterrupt), immediate_transaction(connection):
        connection.execute("INSERT INTO children (id) VALUES (1)")
        raise KeyboardInterrupt
    assert not connection.in_transaction
    assert _child_count(connection) == 0


def test_a_full_database_raises_its_own_error_after_sqlite_rolled_it_back(
    connection: sqlite3.Connection,
) -> None:
    connection.execute("PRAGMA max_page_count = 1")
    with (
        pytest.raises(sqlite3.OperationalError, match="^database or disk is full$"),
        immediate_transaction(connection),
    ):
        connection.execute("INSERT INTO children (id, value) VALUES (1, ?)", (_LONG_VALUE,))
    assert not connection.in_transaction
    assert _child_count(connection) == 0


def test_a_failed_commit_rolls_back_leaving_no_transaction_open(
    connection: sqlite3.Connection,
) -> None:
    with (
        pytest.raises(sqlite3.IntegrityError, match="^FOREIGN KEY constraint failed$"),
        immediate_transaction(connection),
    ):
        connection.execute("INSERT INTO children (id, parent_id) VALUES (1, 404)")
    assert not connection.in_transaction
    assert _child_count(connection) == 0


def test_a_failed_begin_leaves_an_open_transaction_untouched(
    connection: sqlite3.Connection,
) -> None:
    connection.execute("BEGIN")
    connection.execute("INSERT INTO children (id) VALUES (1)")
    with (
        pytest.raises(sqlite3.OperationalError, match="within a transaction"),
        immediate_transaction(connection),
    ):
        pass
    assert connection.in_transaction
    assert _child_count(connection) == 1
