"""``SqliteNodeStateReader`` against its port's contract, seeded through local.db's stores."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from random import Random

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_backoff_state_store import (
    SqliteBackoffStateStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_node_id_store import SqliteNodeIdStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_node_state_reader import (
    SqliteNodeStateReader,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_tracked_download_store import (
    SqliteTrackedDownloadStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import (
    ThreadReadConnections,
)
from p2pwatch.domain.identifiers import NodeId
from tests.contracts.application.ports.driven.node_state_reader_contract import (
    NodeStateReaderContract,
)
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    open_local,
    open_reader,
)
from tests.support.domain.file_target_decision import draw_target_id
from tests.support.domain.observation import draw_file
from tests.support.domain.search.backoff import draw_backoff_key, draw_backoff_state
from tests.support.draws import draw_instant, draw_text


@pytest.fixture
def connection(local_db: Path) -> Iterator[sqlite3.Connection]:
    local = open_local(local_db)
    yield local
    local.close()


@pytest.fixture
def thread_read_connections(local_db: Path) -> Iterator[ThreadReadConnections]:
    with ThreadReadConnections(local_db, open_reader=open_reader) as thread_read_connections:
        yield thread_read_connections


class TestSqliteNodeStateReader(NodeStateReaderContract):
    @pytest.fixture
    def node_id_writer(self, connection: sqlite3.Connection) -> SqliteNodeIdStore:
        return SqliteNodeIdStore(connection)

    @pytest.fixture
    def tracked_download_writer(self, connection: sqlite3.Connection) -> SqliteTrackedDownloadStore:
        return SqliteTrackedDownloadStore(connection)

    @pytest.fixture
    def backoff_state_writer(self, connection: sqlite3.Connection) -> SqliteBackoffStateStore:
        return SqliteBackoffStateStore(connection)

    @pytest.fixture
    def reader(self, thread_read_connections: ThreadReadConnections) -> SqliteNodeStateReader:
        return SqliteNodeStateReader(thread_read_connections)

    @pytest.fixture
    def unreadable_reader(self, unreadable_database: Path) -> Iterator[SqliteNodeStateReader]:
        with ThreadReadConnections(unreadable_database, open_reader=open_reader) as connections:
            yield SqliteNodeStateReader(connections)


@pytest.mark.parametrize(
    "corruption",
    [
        "UPDATE downloads SET state = 'bogus'",
        "UPDATE backoff_states SET delay_seconds = 9e999",
        f"UPDATE node_identity SET created_at_micros = {2**62}",
    ],
    ids=["unknown state", "infinite delay", "creation past year 9999"],
)
def test_a_stored_state_that_cannot_be_read_back_raises_persistence_error(
    *,
    randomness: Random,
    connection: sqlite3.Connection,
    thread_read_connections: ThreadReadConnections,
    corruption: str,
) -> None:
    SqliteNodeIdStore(connection).record_node_id(
        NodeId(draw_text(randomness)), created_at=draw_instant(randomness)
    )
    SqliteTrackedDownloadStore(connection).record_queued(
        draw_file(randomness),
        target_id=draw_target_id(randomness),
        queued_at=draw_instant(randomness),
    )
    SqliteBackoffStateStore(connection).set_backoff_states(
        {draw_backoff_key(randomness, has_channel=True): draw_backoff_state(randomness)}
    )
    connection.execute(corruption)
    with pytest.raises(PersistenceError, match="^a stored value cannot be read: "):
        SqliteNodeStateReader(thread_read_connections).read_node_state()
