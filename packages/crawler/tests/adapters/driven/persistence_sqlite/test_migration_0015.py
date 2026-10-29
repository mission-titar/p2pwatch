"""Catalog 0015 stores a decision's instant as micros, in ``decided_at_micros`` (micros spec)."""

import sqlite3
from pathlib import Path

import pytest

from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import (
    insert_v14_decision,
    open_catalog_at,
)
from tests.support.catalog_rows import file_id, insert_file

_A = "a" * 32
_INDEX = "idx_match_decisions_file_target_decided_at_micros"
# What insert_v14_decision writes besides the id and the stamp.
_COLUMNS = {
    "file_id": file_id(_A),
    "target_id": "062A",
    "rule_name": "exact_062a",
    "tier": "download",
    "node_id": "n1",
}


def _migrated(tmp_path: Path) -> sqlite3.Connection:
    """A catalog at 15 from one at 14 holding two decisions, ids 3 and 7."""
    path = tmp_path / "catalog.db"
    connection = open_catalog_at(path, 14)
    insert_file(connection, _A)
    insert_v14_decision(
        connection, _A, decision_id=3, decided_at="2026-06-11T12:00:00.123456+00:00"
    )
    insert_v14_decision(connection, _A, decision_id=7, decided_at="2026-06-11T12:00:00+00:00")
    connection.close()
    return open_catalog_at(path, 15)


def test_0015_keeps_each_decision_and_converts_its_stamp_to_micros(tmp_path: Path) -> None:
    connection = _migrated(tmp_path)
    try:
        assert rows(
            connection,
            "SELECT id, file_id, target_id, rule_name, tier,"
            " typeof(decided_at_micros) AS decided_at_type, decided_at_micros, node_id"
            " FROM match_decisions ORDER BY id",
        ) == [
            {
                "id": 3,
                **_COLUMNS,
                "decided_at_type": "integer",
                "decided_at_micros": 1_781_179_200_123_456,
            },
            {
                "id": 7,
                **_COLUMNS,
                "decided_at_type": "integer",
                "decided_at_micros": 1_781_179_200_000_000,
            },
        ]
        assert rows(
            connection,
            "SELECT name, type, \"notnull\" FROM pragma_table_info('match_decisions')"
            " WHERE name LIKE 'decided_at%'",
        ) == [{"name": "decided_at_micros", "type": "INTEGER", "notnull": 1}]
        assert rows(connection, "PRAGMA foreign_key_check") == []
        assert rows(connection, "PRAGMA integrity_check") == [{"integrity_check": "ok"}]
    finally:
        connection.close()


def test_0015_keeps_match_decisions_append_only_and_indexed(tmp_path: Path) -> None:
    connection = _migrated(tmp_path)
    try:
        assert rows(connection, "PRAGMA user_version") == [{"user_version": 15}]
        for statement in (
            "UPDATE match_decisions SET tier = 'catalog'",
            "DELETE FROM match_decisions",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="^match_decisions is append-only$"):
                connection.execute(statement)
        assert rows(
            connection, "SELECT name FROM pragma_index_list('match_decisions') WHERE origin = 'c'"
        ) == [{"name": _INDEX}]
        assert rows(
            connection, "SELECT name FROM pragma_index_info(?) ORDER BY seqno", (_INDEX,)
        ) == [
            {"name": "file_id"},
            {"name": "target_id"},
            {"name": "decided_at_micros"},
        ]
    finally:
        connection.close()
