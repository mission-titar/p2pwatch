"""Catalog 0011 recreates stage 4's source tables as variants and points (source points, D8)."""

import sqlite3
from pathlib import Path

from p2pwatch.adapters.persistence_sqlite.connection import open_catalog
from tests.adapters.persistence_sqlite.older_catalog import (
    insert_stage4_range,
    insert_stage4_variant,
    open_catalog_at,
)
from tests.catalog_rows import insert_decision, insert_file, insert_observation, insert_source

_A, _B = "a" * 32, "b" * 32
_USER, _OTHER = "1f2e" * 8, "c" * 32
_KEPT = ("files", "sources", "match_decisions", "observation_variants", "observations")


def _catalog_at_10(path: Path) -> None:
    """Stage 4 rows on two files and two sources, one variant without identity."""
    connection = open_catalog_at(path, 10)
    for ed2k_hash in (_A, _B):
        insert_file(connection, ed2k_hash)
        insert_observation(connection, ed2k_hash, f"{ed2k_hash[0]}.avi")
    insert_decision(connection, _A, "062A", "download")
    for user in (_USER, _OTHER):
        insert_source(connection, user)
    queued = insert_stage4_variant(connection, _A, _USER)
    insert_stage4_range(connection, queued, 10, 20, transfer_counter=7)
    insert_stage4_range(connection, insert_stage4_variant(connection, _B, _OTHER), 30, 30)
    insert_stage4_range(connection, insert_stage4_variant(connection, _B, None), 40, 50)
    connection.close()


def _rows(connection: sqlite3.Connection) -> dict[str, list[tuple[object, ...]]]:
    return {
        table: connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
        for table in _KEPT
    }


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]


def test_0011_drops_the_ranges_and_recreates_the_source_tables_empty(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    _catalog_at_10(path)
    before = open_catalog_at(path, 10)
    kept = _rows(before)
    before.close()
    connection = open_catalog(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 11
        assert _columns(connection, "source_ranges") == []
        assert "node_id" in _columns(connection, "source_variants")
        assert _columns(connection, "source_observations") == [
            "variant_id",
            "observed_at",
            "transfer_counter",
        ]
        for table in ("source_variants", "source_observations"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,)
        assert _rows(connection) == kept
        assert kept["sources"] != []
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
