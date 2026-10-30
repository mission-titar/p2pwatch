import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_backoff_state_store import (
    SqliteBackoffStateStore,
)
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.contracts.application.ports.driven.backoff_state_store_contract import (
    BackoffStateStoreContract,
)
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_local

_STARTED_AT = datetime(2026, 6, 12, 10, 0, 0, 123456, tzinfo=UTC)
_BACKOFF = {
    BackoffKey(client_name=ClientName("amule-1"), channel=Channel("kad")): BackoffState(
        attempts=2, started_at=_STARTED_AT, delay=timedelta(seconds=300)
    ),
    BackoffKey(client_name=ClientName("amule-1"), channel=None): BackoffState(
        attempts=1, started_at=_STARTED_AT, delay=timedelta(seconds=2.75)
    ),
}


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    local = open_local(tmp_path / "local.db")
    yield local
    local.close()


@pytest.fixture
def backoff_state_store(connection: sqlite3.Connection) -> SqliteBackoffStateStore:
    return SqliteBackoffStateStore(connection)


class TestSqliteBackoffStateStore(BackoffStateStoreContract):
    @pytest.fixture
    def backoff_state_store(self, connection: sqlite3.Connection) -> SqliteBackoffStateStore:
        return SqliteBackoffStateStore(connection)


def test_the_backoff_states_saved_are_read_back_by_any_later_instance(
    *, backoff_state_store: SqliteBackoffStateStore, connection: sqlite3.Connection
) -> None:
    # A new instance has no in-memory state: what it loads survived a restart.
    backoff_state_store.set_backoff_states(_BACKOFF)
    reborn = SqliteBackoffStateStore(connection)
    assert reborn.read_backoff_states() == _BACKOFF


def test_a_backoff_state_is_one_row_its_start_in_micros(
    *, backoff_state_store: SqliteBackoffStateStore, connection: sqlite3.Connection
) -> None:
    backoff_state_store.set_backoff_states(_BACKOFF)
    backoff_states = rows(
        connection,
        sql="SELECT client_name, channel, attempts, started_at_micros, delay_seconds"
        " FROM backoff_states"
        " ORDER BY channel",
    )
    started_at_micros = 1_781_258_400_123_456
    assert backoff_states == [
        {
            "client_name": "amule-1",
            "channel": None,
            "attempts": 1,
            "started_at_micros": started_at_micros,
            "delay_seconds": 2.75,
        },
        {
            "client_name": "amule-1",
            "channel": "kad",
            "attempts": 2,
            "started_at_micros": started_at_micros,
            "delay_seconds": 300.0,
        },
    ]


def test_set_backoff_states_is_atomic_on_injected_failure(
    *, backoff_state_store: SqliteBackoffStateStore, connection: sqlite3.Connection
) -> None:
    backoff_state_store.set_backoff_states(_BACKOFF)
    connection.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON backoff_states"
        " WHEN NEW.channel = 'ed2k'"
        " BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    later = {
        BackoffKey(client_name=ClientName("amule-1"), channel=None): BackoffState(
            attempts=2, started_at=_STARTED_AT, delay=timedelta(seconds=4)
        ),
        BackoffKey(client_name=ClientName("amule-1"), channel=Channel("ed2k")): BackoffState(
            attempts=1, started_at=_STARTED_AT, delay=timedelta(seconds=2)
        ),
    }
    with pytest.raises(PersistenceError, match="injected failure"):
        backoff_state_store.set_backoff_states(later)
    assert backoff_state_store.read_backoff_states() == _BACKOFF
