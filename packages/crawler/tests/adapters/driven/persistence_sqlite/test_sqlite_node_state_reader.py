"""``SqliteNodeStateReader`` against its port's contract, seeded through local.db's stores."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

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
from tests.contracts.application.ports.driven.node_state_reader_contract import (
    NodeStateReaderContract,
)
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    open_local,
    open_reader,
)


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
