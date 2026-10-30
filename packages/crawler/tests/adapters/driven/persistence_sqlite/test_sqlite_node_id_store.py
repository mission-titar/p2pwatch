import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_node_id_store import SqliteNodeIdStore
from p2pwatch.domain.identifiers import NodeId
from tests.contracts.application.ports.driven.node_id_store_contract import NodeIdStoreContract
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_local

_START = datetime(2026, 6, 11, 12, 0, 0, 123456, tzinfo=UTC)
_NODE_ID = NodeId("0c9d6b5e-2f4a-4e1b-9a7d-3c2b1a0f9e8d")


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
    node_id_store.record_node_id(_NODE_ID, created_at=_START)

    assert SqliteNodeIdStore(connection).read_node_id() == _NODE_ID


def test_a_recorded_node_id_keeps_its_created_at_as_micros(
    node_id_store: SqliteNodeIdStore, connection: sqlite3.Connection
) -> None:
    node_id_store.record_node_id(_NODE_ID, created_at=_START)

    assert rows(
        connection,
        sql="SELECT typeof(created_at_micros) AS created_at_type, created_at_micros"
        " FROM node_identity",
    ) == [{"created_at_type": "integer", "created_at_micros": instant_to_micros(_START)}]


def test_a_naive_created_at_raises_and_records_nothing(
    node_id_store: SqliteNodeIdStore, connection: sqlite3.Connection
) -> None:
    with pytest.raises(ValueError, match="aware"):
        node_id_store.record_node_id(_NODE_ID, created_at=datetime(2026, 6, 11, 12))
    assert node_id_store.read_node_id() is None
