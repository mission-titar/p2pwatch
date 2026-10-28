"""Catalog 0015 stores a decision's instant as micros, in ``decided_at_micros`` (micros spec)."""

import sqlite3
from pathlib import Path

import pytest

from tests.support.adapters.driven.persistence_sqlite.older_catalog import (
    insert_v14_decision,
    open_catalog_at,
)
from tests.support.catalog_rows import file_id, insert_file

_A = "a" * 32
_INDEX = "idx_match_decisions_file_target_decided_at_micros"
# What insert_v14_decision writes between the id and the stamp.
_COLUMNS = (file_id(_A), "062A", "exact_062a", "download")


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
        assert connection.execute(
            "SELECT id, file_id, target_id, rule_name, tier, typeof(decided_at_micros),"
            " decided_at_micros, node_id FROM match_decisions ORDER BY id"
        ).fetchall() == [
            (3, *_COLUMNS, "integer", 1_781_179_200_123_456, "n1"),
            (7, *_COLUMNS, "integer", 1_781_179_200_000_000, "n1"),
        ]
        assert connection.execute(
            "SELECT name, type, \"notnull\" FROM pragma_table_info('match_decisions')"
            " WHERE name LIKE 'decided_at%'"
        ).fetchall() == [("decided_at_micros", "INTEGER", 1)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        connection.close()


def test_0015_keeps_match_decisions_append_only_and_indexed(tmp_path: Path) -> None:
    connection = _migrated(tmp_path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 15
        for statement in (
            "UPDATE match_decisions SET tier = 'catalog'",
            "DELETE FROM match_decisions",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="^match_decisions is append-only$"):
                connection.execute(statement)
        assert connection.execute(
            "SELECT name FROM pragma_index_list('match_decisions') WHERE origin = 'c'"
        ).fetchall() == [(_INDEX,)]
        assert connection.execute(
            "SELECT name FROM pragma_index_info(?) ORDER BY seqno", (_INDEX,)
        ).fetchall() == [("file_id",), ("target_id",), ("decided_at_micros",)]
    finally:
        connection.close()
