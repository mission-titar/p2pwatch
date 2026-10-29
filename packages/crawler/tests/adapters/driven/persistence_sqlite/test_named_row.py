import sqlite3
from collections.abc import Iterator

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.named_row import NamedRow, named_row


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = named_row
    yield connection
    connection.close()


def _row(connection: sqlite3.Connection) -> NamedRow:
    row: NamedRow = connection.execute("SELECT 1 AS a, 'x' AS b").fetchone()
    return row


def test_a_row_is_read_by_column_name(connection: sqlite3.Connection) -> None:
    row = _row(connection)
    assert row["a"] == 1
    assert row["b"] == "x"
    assert row == {"a": 1, "b": "x"}
    assert dict(row) == {"a": 1, "b": "x"}
    assert list(row.items()) == [("a", 1), ("b", "x")]


def test_a_read_by_index_raises(connection: sqlite3.Connection) -> None:
    with pytest.raises(KeyError):
        connection.execute("SELECT 1 AS a").fetchone()[0]


def test_unpacking_a_row_raises(connection: sqlite3.Connection) -> None:
    row = _row(connection)
    with pytest.raises(TypeError, match="by column name"):
        a, b = row
    with pytest.raises(TypeError, match="by column name"):
        print(*row)


def test_a_column_name_that_appears_twice_is_refused(connection: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="'a' appears twice"):
        connection.execute("SELECT 1 AS a, 2 AS b, 3 AS a").fetchone()
