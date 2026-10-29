"""Catalog 0009 gives back the pages the rewrite freed, outside a transaction (stage 1, D7, D8)."""

import sqlite3
from pathlib import Path

from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import open_catalog_at
from tests.support.catalog_rows import insert_file

_HASH = "a" * 32


def _catalog_at_8_with_free_pages(path: Path) -> None:
    connection = open_catalog_at(path, 8)
    insert_file(connection, _HASH, 1)
    # Stands for the tables 0006 to 0008 dropped.
    connection.execute(
        "CREATE TABLE dropped AS WITH RECURSIVE n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n"
        " WHERE i < 64) SELECT randomblob(4096) FROM n"
    )
    connection.execute("DROP TABLE dropped")
    assert rows(connection, "PRAGMA freelist_count")[0]["freelist_count"] > 0
    connection.close()


def test_0009_vacuums_the_free_pages_away_and_keeps_the_rows(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    _catalog_at_8_with_free_pages(path)

    connection = open_catalog_at(path, 9)
    try:
        assert rows(connection, "PRAGMA user_version") == [{"user_version": 9}]
        assert rows(connection, "PRAGMA freelist_count") == [{"freelist_count": 0}]
        assert rows(connection, "SELECT native_id FROM files") == [{"native_id": _HASH}]
    finally:
        connection.close()


def test_0009_is_safe_to_replay(tmp_path: Path) -> None:
    """A stop between the VACUUM and the stamp runs it again at the next start."""
    path = tmp_path / "catalog.db"
    open_catalog_at(path, 9).close()
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA user_version = 8")
    raw.close()

    connection = open_catalog_at(path, 9)
    try:
        assert rows(connection, "PRAGMA user_version") == [{"user_version": 9}]
    finally:
        connection.close()


def test_0009_leaves_the_wal_truncated(tmp_path: Path) -> None:
    """The crawler keeps its connection open, so a WAL the VACUUM grew would stay on disk."""
    path = tmp_path / "catalog.db"
    _catalog_at_8_with_free_pages(path)

    connection = open_catalog_at(path, 9)
    try:
        page_size = rows(connection, "PRAGMA page_size")[0]["page_size"]
        # The WAL header, then the one frame of the user_version stamp that follows 0009.
        assert Path(f"{path}-wal").stat().st_size <= 32 + 24 + page_size
    finally:
        connection.close()
