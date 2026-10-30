"""Local 0015 replaces ``node_runtime`` with ``node_identity`` and leaves every table STRICT."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.errors import MigrationError
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import open_local_at

_NODE_ID = "0c9d6b5e-2f4a-4e1b-9a7d-3c2b1a0f9e8d"


def _local_at_14(path: Path, node_runtime: list[tuple[str, str]]) -> None:
    with closing(open_local_at(path, version=14)) as connection:
        connection.executemany("INSERT INTO node_runtime (key, value) VALUES (?, ?)", node_runtime)
        connection.execute(
            "INSERT INTO reevaluation_state (id, policy_fingerprint) VALUES (1, 'sha256:abc')"
        )


def test_0015_moves_the_node_identity_into_one_typed_row(tmp_path: Path) -> None:
    path = tmp_path / "local.db"
    _local_at_14(
        path,
        [("node_id", _NODE_ID), ("created_at", "2026-06-11T12:00:00.123456+00:00"), ("x", "y")],
    )

    with closing(open_local_at(path, version=15)) as connection:
        assert rows(connection, sql="PRAGMA user_version") == [{"user_version": 15}]
        assert rows(connection, sql="SELECT * FROM node_identity") == [
            {"id": 1, "node_id": _NODE_ID, "created_at_micros": 1_781_179_200_123_456}
        ]
        assert rows(connection, sql="SELECT * FROM reevaluation_state") == [
            {"id": 1, "policy_fingerprint": "sha256:abc"}
        ]
        assert (
            rows(connection, sql="SELECT name FROM sqlite_master WHERE name = 'node_runtime'") == []
        )
        assert rows(connection, sql="PRAGMA integrity_check") == [{"integrity_check": "ok"}]


def test_0015_leaves_every_table_strict(tmp_path: Path) -> None:
    path = tmp_path / "local.db"
    _local_at_14(path, [])

    with closing(open_local_at(path, version=15)) as connection:
        assert (
            rows(
                connection,
                sql="SELECT name FROM pragma_table_list WHERE schema = 'main' AND type = 'table'"
                " AND NOT strict AND name NOT LIKE 'sqlite_%'",
            )
            == []
        )
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            connection.execute("INSERT INTO node_identity VALUES (2, 'n', 0)")
        with pytest.raises(sqlite3.IntegrityError, match="cannot store TEXT value"):
            connection.execute("INSERT INTO node_identity VALUES (1, 'n', '2026-06-11')")


def test_0015_refuses_a_node_id_without_its_created_at(tmp_path: Path) -> None:
    path = tmp_path / "local.db"
    _local_at_14(path, [("node_id", _NODE_ID)])

    with pytest.raises(
        MigrationError, match="NOT NULL constraint failed: node_identity.created_at_micros"
    ):
        open_local_at(path, version=15)

    with closing(sqlite3.connect(path)) as raw:
        assert rows(raw, sql="PRAGMA user_version") == [{"user_version": 14}]
        assert rows(raw, sql="SELECT key, value FROM node_runtime") == [
            {"key": "node_id", "value": _NODE_ID}
        ]
