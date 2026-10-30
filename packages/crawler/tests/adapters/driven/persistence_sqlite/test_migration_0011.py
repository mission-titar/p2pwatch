"""Catalog 0011 recreates stage 4's source tables as variants and points (source points, D8)."""

import sqlite3
from pathlib import Path
from typing import Any

from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import (
    insert_stage4_range,
    insert_stage4_variant,
    insert_v11_observation,
    insert_v14_decision,
    open_catalog_at,
)
from tests.support.catalog_rows import insert_file, insert_source

_A, _B = "a" * 32, "b" * 32
_USER, _OTHER = "1f2e" * 8, "c" * 32
_KEPT = ("files", "sources", "match_decisions", "observation_variants", "observations")


def _catalog_at_10(path: Path) -> None:
    """Stage 4 rows on two files and two sources, one variant without identity."""
    connection = open_catalog_at(path, version=10)
    for native_id in (_A, _B):
        insert_file(connection, native_id=native_id)
        insert_v11_observation(connection, native_id=native_id, filename=f"{native_id[0]}.avi")
    insert_v14_decision(connection, native_id=_A)
    for user in (_USER, _OTHER):
        insert_source(connection, user_hash=user)
    queued = insert_stage4_variant(connection, native_id=_A, user_hash=_USER)
    insert_stage4_range(
        connection, variant_id=queued, first_seen_at=10, last_seen_at=20, transfer_counter=7
    )
    insert_stage4_range(
        connection,
        variant_id=insert_stage4_variant(connection, native_id=_B, user_hash=_OTHER),
        first_seen_at=30,
        last_seen_at=30,
    )
    insert_stage4_range(
        connection,
        variant_id=insert_stage4_variant(connection, native_id=_B, user_hash=None),
        first_seen_at=40,
        last_seen_at=50,
    )
    connection.close()


def _kept_rows(connection: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    return {table: rows(connection, sql=f"SELECT * FROM {table} ORDER BY 1, 2") for table in _KEPT}


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [column["name"] for column in rows(connection, sql=f"PRAGMA table_info({table})")]


def test_0011_drops_the_ranges_and_recreates_the_source_tables_empty(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    _catalog_at_10(path)
    before = open_catalog_at(path, version=10)
    kept = _kept_rows(before)
    before.close()
    connection = open_catalog_at(path, version=11)
    try:
        assert rows(connection, sql="PRAGMA user_version") == [{"user_version": 11}]
        assert _columns(connection, "source_ranges") == []
        assert "node_id" in _columns(connection, "source_variants")
        assert _columns(connection, "source_observations") == [
            "variant_id",
            "observed_at",
            "transfer_counter",
        ]
        for table in ("source_variants", "source_observations"):
            assert rows(connection, sql=f"SELECT COUNT(*) AS row_count FROM {table}") == [
                {"row_count": 0}
            ]
        assert _kept_rows(connection) == kept
        assert kept["sources"] != []
        assert rows(connection, sql="PRAGMA foreign_key_check") == []
    finally:
        connection.close()
