import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_local


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    local = open_local(tmp_path / "local.db")
    yield local
    local.close()


def test_downloads_has_size_bytes_column(connection: sqlite3.Connection) -> None:
    columns = {column["name"] for column in rows(connection, sql="PRAGMA table_info(downloads)")}
    assert "size_bytes" in columns


def test_user_version_is_at_least_two(connection: sqlite3.Connection) -> None:
    assert rows(connection, sql="PRAGMA user_version")[0]["user_version"] >= 2
