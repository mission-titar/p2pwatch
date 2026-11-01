"""D4's and D5's reads of a source's history on a real catalog (source points spec, section 7)."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_source_point_store import (
    SqliteSourcePointStore,
)
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.json_object_text import JsonObjectText
from p2pwatch.domain.source import LatestPoint, SourceKey, SourceReading
from tests.contracts.application.ports.driven.source_point_store_contract import (
    SourcePointStoreContract,
)
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_catalog
from tests.support.catalog_rows import (
    file_id,
    insert_file,
    insert_source,
    insert_source_point,
    insert_source_variant,
)

_FILE, _OTHER_FILE = "a" * 32, "b" * 32
_USER, _OTHER_USER = "1f2e" * 8, "c" * 32
_KEY, _OTHER_KEY = (
    SourceKey(network=Network.ED2K, native_id=_USER),
    SourceKey(network=Network.ED2K, native_id=_OTHER_USER),
)
_T0 = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_NODE_ID = NodeId("n1")


def _us(moment: datetime) -> int:
    return (moment - _EPOCH) // timedelta(microseconds=1)


def _points(catalog: sqlite3.Connection, *moments: datetime) -> None:
    variant_id = insert_source_variant(catalog, native_id=_FILE, user_hash=_USER)
    for moment in moments:
        insert_source_point(
            catalog, variant_id=variant_id, observed_at_micros=_us(moment), session_received_bytes=0
        )


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(tmp_path / "catalog.db")
    yield catalog
    catalog.close()


@pytest.fixture
def catalog(connection: sqlite3.Connection) -> sqlite3.Connection:
    for native_id in (_FILE, _OTHER_FILE):
        insert_file(connection, native_id=native_id)
    for user_hash in (_USER, _OTHER_USER):
        insert_source(connection, user_hash=user_hash)
    return connection


@pytest.fixture
def source_point_store(catalog: sqlite3.Connection) -> SqliteSourcePointStore:
    return SqliteSourcePointStore(catalog)


class TestSqliteSourcePointStore(SourcePointStoreContract):
    @pytest.fixture
    def observation_writer(self, connection: sqlite3.Connection) -> SqliteObservationStore:
        return SqliteObservationStore(connection)

    @pytest.fixture
    def source_point_store(self, connection: sqlite3.Connection) -> SqliteSourcePointStore:
        # Without the module's raw rows: the contract seeds only through the Writers.
        return SqliteSourcePointStore(connection)

    @pytest.fixture
    def writer(self, source_point_store: SqliteSourcePointStore) -> SqliteSourcePointStore:
        return source_point_store

    @pytest.fixture
    def reader(self, source_point_store: SqliteSourcePointStore) -> SqliteSourcePointStore:
        return source_point_store


def _passing() -> SourceReading:
    return SourceReading(
        source=_KEY,
        source_name="AnimuseeFMR",
        software=None,
        role=None,
        contact_point=None,
        connectable=None,
        raw_metadata=JsonObjectText(text="{}"),
        session_received_bytes=0,
    )


def _latest(
    source_point_store: SqliteSourcePointStore,
    *,
    reading: SourceReading,
    since: datetime,
    before: datetime,
) -> LatestPoint | None:
    file = FileKey(network=Network.ED2K, native_id=_FILE)
    return source_point_store.read_latest_point(
        file, reading=reading, since=since, before=before, node_id=_NODE_ID
    )


class MeasuredRead(Protocol):
    def __call__(self) -> object: ...


def _steps(connection: sqlite3.Connection, *, read: MeasuredRead) -> int:
    """The SQLite VM instructions ``read`` runs."""
    steps = 0

    def count() -> int:
        nonlocal steps
        steps += 1
        return 0

    connection.set_progress_handler(count, 1)
    read()
    connection.set_progress_handler(None, 1)
    return steps


def _other_variants(catalog: sqlite3.Connection, *, numbers: range) -> None:
    """Other peers' variants on this node, which an index on ``node_id`` alone would walk."""
    catalog.executemany(
        "INSERT INTO source_variants (file_id, name, role, raw_metadata, node_id, content_hash)"
        " VALUES (?, ?, 'queued', '{}', 'n1', ?)",
        ((file_id(_OTHER_FILE), f"peer {n}", n.to_bytes(16)) for n in numbers),
    )


def test_earlier_points_seek_once_per_variant_whatever_the_history(
    catalog: sqlite3.Connection,
) -> None:
    # A year at 5 minutes is about 100k points: the reads must not walk them.
    before = _T0 + timedelta(days=400)
    for user, count in ((_USER, 1_000), (_OTHER_USER, 100_000)):
        for role in ("queued", "nothing_new"):
            variant_id = insert_source_variant(catalog, native_id=_FILE, user_hash=user, role=role)
            catalog.executemany(
                "INSERT INTO source_observations VALUES (?, ?, 0)",
                ((variant_id, _us(_T0) + n * 300_000_000) for n in range(count // 2)),
            )
    source_point_store = SqliteSourcePointStore(catalog)
    source_point_store.read_earlier_points(
        _KEY, before=before, node_id=NodeId("n1")
    )  # the first call prepares the statement
    small = _steps(
        catalog,
        read=lambda: source_point_store.read_earlier_points(
            _KEY, before=before, node_id=NodeId("n1")
        ),
    )
    large = _steps(
        catalog,
        read=lambda: source_point_store.read_earlier_points(
            _OTHER_KEY, before=before, node_id=NodeId("n1")
        ),
    )
    assert abs(large - small) <= small // 10


def test_earlier_points_seek_this_sources_variants_whatever_the_node_holds(
    *, source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    _points(catalog, _T0)
    _other_variants(catalog, numbers=range(100))
    source_point_store.read_earlier_points(
        _KEY, before=_T0, node_id=NodeId("n1")
    )  # the first call prepares the statement
    small = _steps(
        catalog,
        read=lambda: source_point_store.read_earlier_points(
            _KEY, before=_T0 + timedelta(hours=1), node_id=NodeId("n1")
        ),
    )
    _other_variants(catalog, numbers=range(100, 10_000))
    large = _steps(
        catalog,
        read=lambda: source_point_store.read_earlier_points(
            _KEY, before=_T0 + timedelta(hours=1), node_id=NodeId("n1")
        ),
    )
    assert abs(large - small) <= small // 10


def test_the_latest_point_seeks_this_sources_variants_whatever_the_node_holds(
    *, source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    _points(catalog, _T0)
    _other_variants(catalog, numbers=range(100))
    since, before = _T0, _T0 + timedelta(seconds=30)
    _latest(
        source_point_store, reading=_passing(), since=since, before=before
    )  # the first call prepares the statement
    small = _steps(
        catalog,
        read=lambda: _latest(source_point_store, reading=_passing(), since=since, before=before),
    )
    _other_variants(catalog, numbers=range(100, 10_000))
    large = _steps(
        catalog,
        read=lambda: _latest(source_point_store, reading=_passing(), since=since, before=before),
    )
    assert abs(large - small) <= small // 10
