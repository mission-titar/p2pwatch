"""Local 0011 replaces scheduler_state with a typed backoff_states (monotonic clock spec, D8)."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.support.adapters.driven.persistence_sqlite.older_catalog import open_local_at

_INSERT = "INSERT INTO backoff_states VALUES (?, ?, ?, ?, ?)"


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    local = open_local_at(tmp_path / "local.db", 11)
    yield local
    local.close()


def test_0011_creates_a_strict_backoff_states_and_drops_scheduler_state(
    connection: sqlite3.Connection,
) -> None:
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 11
    tables = connection.execute(
        "SELECT name, strict FROM pragma_table_list"
        " WHERE name IN ('backoff_states', 'scheduler_state')"
    ).fetchall()
    assert tables == [("backoff_states", 1)]


@pytest.mark.parametrize(
    "row",
    [
        ("amule-1", None, 1, "x", 1.0),
        ("amule-1", None, 0, 0, 1.0),
        ("amule-1", None, 1, 0, -1.0),
    ],
    ids=["started_at", "attempts", "delay_seconds"],
)
def test_0011_refuses_a_row_of_the_wrong_shape(
    connection: sqlite3.Connection, row: tuple[object, ...]
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(_INSERT, row)


def test_0011_holds_one_row_per_client_and_channel_a_null_channel_included(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(_INSERT, ("amule-1", None, 1, 0, 1.0))
    connection.execute(_INSERT, ("amule-1", "kad", 1, 0, 1.0))
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        connection.execute(_INSERT, ("amule-1", None, 2, 0, 1.0))


def test_0011_drops_the_backoff_pending_at_the_upgrade(tmp_path: Path) -> None:
    path = tmp_path / "local.db"
    connection = open_local_at(path, 10)
    connection.execute(
        "INSERT INTO scheduler_state (key, value) VALUES ('backoff_states', ?)",
        ('{"amuled:kad": {"attempts": 2, "retry_after": "2026-10-13T00:03:00.000000+00:00"}}',),
    )
    connection.close()

    connection = open_local_at(path, 11)
    try:
        assert connection.execute("SELECT * FROM backoff_states").fetchall() == []
    finally:
        connection.close()
