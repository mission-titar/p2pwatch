import sqlite3
from collections.abc import Iterator

import pytest

from tests.support.adapters.driven.persistence_sqlite.named_row import rows


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
