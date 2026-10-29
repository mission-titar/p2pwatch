import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_local


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


def test_rows_are_plain_dicts_by_column_name(connection: sqlite3.Connection) -> None:
    read = rows(connection, "SELECT ? AS a, 'x' AS b UNION ALL SELECT 2, 'y'", (1,))
    assert read == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    assert {type(row) for row in read} == {dict}


def test_a_column_name_that_appears_twice_is_refused(connection: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="'a' appears twice"):
        rows(connection, "SELECT 1 AS a, 2 AS a")


def test_rows_of_a_connection_reading_by_column_name_are_plain_dicts(tmp_path: Path) -> None:
    with closing(open_local(tmp_path / "local.db")) as connection:
        read = rows(connection, "SELECT 1 AS a")
    assert read == [{"a": 1}]
    assert type(read[0]) is dict
