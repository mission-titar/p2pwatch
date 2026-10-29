"""Catalog 0006 drops the dead tables, and refuses a catalog whose ranges hold a row (stage 1, D6).

A compacted day cannot become observations: it keeps no keyword, duration, bitrate or raw_meta.
"""

import sqlite3
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.errors import MigrationError
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import open_catalog_at
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_catalog

_HASH = "a" * 32
_DEAD_TABLES = ("source_observations", "sources", "file_observation_ranges")
_RANGE = (
    "INSERT INTO file_observation_ranges (ed2k_hash, bucket, filenames, node_ids,"
    " observation_count, first_observed_at, last_observed_at, source_count_min,"
    " source_count_max, source_count_sum, complete_source_count_min,"
    " complete_source_count_max, complete_source_count_sum) VALUES"
    f" ('{_HASH}', '2026-03-01', '[\"f.avi\"]', '[\"n\"]', 1,"
    " '2026-03-01T00:00:00.000000+00:00', '2026-03-01T00:00:00.000000+00:00',"
    " 1, 1, 1, 0, 0, 0)"
)


def _write_catalog_at_5(path: Path, *, with_range: bool) -> None:
    connection = open_catalog_at(path, 5)
    connection.execute(f"INSERT INTO files (ed2k_hash, size_bytes) VALUES ('{_HASH}', 1)")
    if with_range:
        connection.execute(_RANGE)
    connection.close()


def _schema_names(connection: sqlite3.Connection) -> set[str]:
    schema = rows(connection, "SELECT name, tbl_name FROM sqlite_schema")
    return {str(name) for row in schema for name in row.values()}


def test_a_catalog_holding_ranges_refuses_to_migrate(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    _write_catalog_at_5(path, with_range=True)

    with pytest.raises(MigrationError, match="file_observation_ranges"):
        open_catalog(path)

    raw = sqlite3.connect(path)
    try:
        assert rows(raw, "PRAGMA user_version") == [{"user_version": 5}]
        assert rows(raw, "SELECT count(*) AS range_count FROM file_observation_ranges") == [
            {"range_count": 1}
        ]
    finally:
        raw.close()


def test_a_catalog_without_ranges_drops_the_dead_tables_and_keeps_its_files(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.db"
    _write_catalog_at_5(path, with_range=False)

    connection = open_catalog_at(path, 6)
    try:
        assert rows(connection, "PRAGMA user_version") == [{"user_version": 6}]
        assert not _schema_names(connection) & {*_DEAD_TABLES, "migration_0006_guard"}
        assert rows(connection, "SELECT ed2k_hash FROM files") == [{"ed2k_hash": _HASH}]
    finally:
        connection.close()
