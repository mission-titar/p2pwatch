import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.persistence_sqlite.backoff_state_repository import (
    SqliteBackoffStateRepository,
)
from p2pwatch.adapters.persistence_sqlite.connection import open_local
from p2pwatch.adapters.persistence_sqlite.errors import PersistenceError
from p2pwatch.ports.backoff_state_repository import BackoffKey, BackoffState

_STARTED_AT = datetime(2026, 6, 12, 10, 0, 0, 123456, tzinfo=UTC)
_BACKOFF = {
    BackoffKey("amule-1", "kad"): BackoffState(2, _STARTED_AT, timedelta(seconds=300)),
    BackoffKey("amule-1", None): BackoffState(1, _STARTED_AT, timedelta(seconds=2.75)),
}


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    local = open_local(tmp_path / "local.db")
    yield local
    local.close()


@pytest.fixture
def repository(connection: sqlite3.Connection) -> SqliteBackoffStateRepository:
    return SqliteBackoffStateRepository(connection)


def test_load_backoff_states_is_empty_on_a_fresh_database(
    repository: SqliteBackoffStateRepository,
) -> None:
    assert repository.load_backoff_states() == {}


def test_backoff_states_round_trip_through_a_new_repo_instance(
    repository: SqliteBackoffStateRepository, connection: sqlite3.Connection
) -> None:
    # A new instance has no in-memory state: what it loads survived a restart.
    repository.save_backoff_states(_BACKOFF)
    reborn = SqliteBackoffStateRepository(connection)
    assert reborn.load_backoff_states() == _BACKOFF


def test_a_backoff_state_is_one_row_its_start_in_micros(
    repository: SqliteBackoffStateRepository, connection: sqlite3.Connection
) -> None:
    repository.save_backoff_states(_BACKOFF)
    rows = connection.execute(
        "SELECT client_name, channel, attempts, started_at, delay_seconds FROM backoff_states"
        " ORDER BY channel"
    ).fetchall()
    started_at_micros = 1_781_258_400_123_456
    assert rows == [
        ("amule-1", None, 1, started_at_micros, 2.75),
        ("amule-1", "kad", 2, started_at_micros, 300.0),
    ]


def test_save_backoff_states_replaces_the_whole_table(
    repository: SqliteBackoffStateRepository,
) -> None:
    repository.save_backoff_states(_BACKOFF)
    repository.save_backoff_states({})  # empty snapshot → replaces everything
    assert repository.load_backoff_states() == {}


def test_save_backoff_states_is_atomic_on_injected_failure(
    repository: SqliteBackoffStateRepository, connection: sqlite3.Connection
) -> None:
    repository.save_backoff_states(_BACKOFF)
    connection.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON backoff_states"
        " WHEN NEW.channel = 'ed2k'"
        " BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    later = {
        BackoffKey("amule-1", None): BackoffState(2, _STARTED_AT, timedelta(seconds=4)),
        BackoffKey("amule-1", "ed2k"): BackoffState(1, _STARTED_AT, timedelta(seconds=2)),
    }
    with pytest.raises(PersistenceError, match="injected failure"):
        repository.save_backoff_states(later)
    assert repository.load_backoff_states() == _BACKOFF
