import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_node_id_store import SqliteNodeIdStore
from tests.contracts.application.ports.driven.node_id_store_contract import NodeIdStoreContract
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_local

_START = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
_NODE_ID = "0c9d6b5e-2f4a-4e1b-9a7d-3c2b1a0f9e8d"


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    local = open_local(tmp_path / "local.db")
    yield local
    local.close()


@pytest.fixture
def node_id_store(connection: sqlite3.Connection) -> SqliteNodeIdStore:
    return SqliteNodeIdStore(connection)


class TestSqliteNodeIdStore(NodeIdStoreContract):
    @pytest.fixture
    def node_id_store(self, connection: sqlite3.Connection) -> SqliteNodeIdStore:
        return SqliteNodeIdStore(connection)


def test_a_recorded_node_id_is_read_back_by_any_later_instance(
    node_id_store: SqliteNodeIdStore, connection: sqlite3.Connection
) -> None:
    node_id_store.record_node_id(_NODE_ID, _START)

    assert SqliteNodeIdStore(connection).read_node_id() == _NODE_ID


def test_a_recorded_node_id_keeps_its_created_at_alongside(
    node_id_store: SqliteNodeIdStore, connection: sqlite3.Connection
) -> None:
    node_id_store.record_node_id(_NODE_ID, _START)

    row = connection.execute("SELECT value FROM node_runtime WHERE key = 'created_at'").fetchone()
    assert row == ("2026-06-11T12:00:00.000000+00:00",)


def test_a_failed_record_is_rolled_back_whole(
    node_id_store: SqliteNodeIdStore, connection: sqlite3.Connection
) -> None:
    # 'created_at' pre-existing -> the two-row INSERT violates the PK -> full rollback.
    connection.execute("INSERT INTO node_runtime (key, value) VALUES ('created_at', 'already')")
    with pytest.raises(PersistenceError, match="UNIQUE"):
        node_id_store.record_node_id(_NODE_ID, _START)
    assert node_id_store.read_node_id() is None


def test_a_naive_created_at_does_not_wedge_the_connection(
    node_id_store: SqliteNodeIdStore, connection: sqlite3.Connection
) -> None:
    # utc_iso raises ValueError on a naive instant; a NON-sqlite failure must
    # NEVER leave the connection in_transaction (otherwise every subsequent call dies with
    # "cannot start a transaction within a transaction", a misleading diagnostic).
    with pytest.raises(ValueError, match="aware"):
        node_id_store.record_node_id(_NODE_ID, datetime(2026, 6, 11, 12))
    assert connection.in_transaction is False  # healthy connection, no zombie transaction
    assert node_id_store.read_node_id() is None  # nothing half-written
    node_id_store.record_node_id(_NODE_ID, _START)  # the connection stays usable
    assert node_id_store.read_node_id() == _NODE_ID
