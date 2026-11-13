import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_search_start_store import (
    SqliteSearchStartStore,
)
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.latest_search_start import LatestSearchStart
from tests.contracts.application.ports.driven.search_start_store_contract import (
    SearchStartStoreContract,
)
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.refused_writes import (
    StorageRefusal,
    refusing,
)
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_local
from tests.support.refused_writes import RefuseWrites

_START = LatestSearchStart(
    channel=Channel("kad"),
    scope="keroro",
    started_at=datetime(2026, 6, 12, 10, 0, 0, 123456, tzinfo=UTC),
)


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    local = open_local(tmp_path / "local.db")
    yield local
    local.close()


@pytest.fixture
def search_start_store(connection: sqlite3.Connection) -> SqliteSearchStartStore:
    return SqliteSearchStartStore(connection)


class TestSqliteSearchStartStore(SearchStartStoreContract):
    @pytest.fixture
    def writer(self, search_start_store: SqliteSearchStartStore) -> SqliteSearchStartStore:
        return search_start_store

    @pytest.fixture
    def reader(self, search_start_store: SqliteSearchStartStore) -> SqliteSearchStartStore:
        return search_start_store

    @pytest.fixture(params=list(StorageRefusal), ids=str)
    def refuse_writes(
        self, *, request: pytest.FixtureRequest, connection: sqlite3.Connection
    ) -> RefuseWrites:
        return refusing(connection, refusal=request.param)


def test_the_starts_written_are_read_back_by_any_later_instance(
    *, search_start_store: SqliteSearchStartStore, connection: sqlite3.Connection
) -> None:
    # A new instance has no in-memory state: what it reads survived a restart.
    search_start_store.set_latest_start(ClientName("amuled"), start=_START)
    reborn = SqliteSearchStartStore(connection)
    assert reborn.read_latest_starts(ClientName("amuled")) == (_START,)


def test_a_start_is_one_row_its_instant_in_micros(
    *, search_start_store: SqliteSearchStartStore, connection: sqlite3.Connection
) -> None:
    search_start_store.set_latest_start(ClientName("amuled"), start=_START)
    assert rows(
        connection,
        sql="SELECT client_name, channel, scope, started_at_micros FROM latest_search_starts",
    ) == [
        {
            "client_name": "amuled",
            "channel": "kad",
            "scope": "keroro",
            "started_at_micros": 1_781_258_400_123_456,
        }
    ]


def test_a_stored_instant_no_datetime_holds_raises_persistence_error(
    *, search_start_store: SqliteSearchStartStore, connection: sqlite3.Connection
) -> None:
    connection.execute(
        "INSERT INTO latest_search_starts VALUES ('amuled', 'ed2k', '', 9223372036854775807)"
    )
    with pytest.raises(PersistenceError, match="a stored value cannot be read"):
        search_start_store.read_latest_starts(ClientName("amuled"))
