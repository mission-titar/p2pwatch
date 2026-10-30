"""D4's and D5's reads of a source's history on a real catalog (source points spec, section 7)."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_source_point_store import (
    SqliteSourcePointStore,
)
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.source import LatestPoint, SourceKey, SourceReading, SourceRole
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


def _points(
    catalog: sqlite3.Connection,
    *moments: datetime,
    role: str = "queued",
    native_id: str = _FILE,
    user_hash: str | None = _USER,
    name: str = "AnimuseeFMR",
    node_id: str = "n1",
    session_received_bytes: int = 0,
) -> None:
    variant_id = insert_source_variant(
        catalog, native_id=native_id, user_hash=user_hash, name=name, role=role, node_id=node_id
    )
    for moment in moments:
        insert_source_point(
            catalog,
            variant_id=variant_id,
            observed_at_micros=_us(moment),
            session_received_bytes=session_received_bytes,
        )


@pytest.fixture
def catalog(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_catalog(tmp_path / "catalog.db")
    for native_id in (_FILE, _OTHER_FILE):
        insert_file(connection, native_id=native_id)
    for user_hash in (_USER, _OTHER_USER):
        insert_source(connection, user_hash=user_hash)
    yield connection
    connection.close()


@pytest.fixture
def source_point_store(catalog: sqlite3.Connection) -> SqliteSourcePointStore:
    return SqliteSourcePointStore(catalog)


def _passing(key: SourceKey | None = _KEY, name: str = "AnimuseeFMR") -> SourceReading:
    return SourceReading(
        source=key,
        source_name=name,
        software=None,
        role=None,
        contact_point=None,
        connectable=None,
        raw_metadata=(),
        session_received_bytes=0,
    )


def _latest(
    source_point_store: SqliteSourcePointStore,
    reading: SourceReading,
    since: datetime,
    before: datetime,
    *,
    native_id: str = _FILE,
    node_id: NodeId = _NODE_ID,
) -> LatestPoint | None:
    file = FileKey(network=Network.ED2K, native_id=native_id)
    return source_point_store.read_latest_point(
        file, reading=reading, since=since, before=before, node_id=node_id
    )


def test_the_latest_point_is_the_latest_since_the_window_opens_before_it_closes(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    later = _T0 + timedelta(seconds=30)
    _points(catalog, _T0, role="nothing_new", session_received_bytes=5)
    _points(catalog, later, role="sending", session_received_bytes=7)
    assert _latest(source_point_store, _passing(), _T0, later) == LatestPoint(
        role=SourceRole.NOTHING_NEW, observed_at=_T0, session_received_bytes=5
    )
    assert _latest(source_point_store, _passing(), _T0 + timedelta(microseconds=1), later) is None
    assert _latest(source_point_store, _passing(), _T0, later + timedelta(seconds=1)) == (
        LatestPoint(role=SourceRole.SENDING, observed_at=later, session_received_bytes=7)
    )


def test_a_reading_without_identity_reads_only_its_name_without_identity(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    before = _T0 + timedelta(seconds=30)
    _points(catalog, _T0, role="nothing_new")
    _points(catalog, _T0, role="sending", user_hash=None)
    _points(catalog, _T0, role="standby", user_hash=None, name="Teammate")
    assert _latest(source_point_store, _passing(_KEY, "Renamed"), _T0, before) == LatestPoint(
        role=SourceRole.NOTHING_NEW, observed_at=_T0, session_received_bytes=0
    )
    assert _latest(source_point_store, _passing(None), _T0, before) == LatestPoint(
        role=SourceRole.SENDING, observed_at=_T0, session_received_bytes=0
    )
    assert _latest(source_point_store, _passing(None, "Nobody"), _T0, before) is None


def test_the_latest_point_reads_this_file_on_the_given_node_only(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    before = _T0 + timedelta(seconds=30)
    _points(catalog, _T0, role="sending", native_id=_OTHER_FILE)
    _points(catalog, _T0, role="nothing_new", node_id="n2")
    assert _latest(source_point_store, _passing(), _T0, before) is None
    assert _latest(
        source_point_store, _passing(), _T0, before, node_id=NodeId("n2")
    ) == LatestPoint(role=SourceRole.NOTHING_NEW, observed_at=_T0, session_received_bytes=0)


def test_earlier_points_are_each_variants_latest_point_before_the_round(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    round_started_at = _T0 + timedelta(hours=3)
    _points(catalog, _T0, _T0 + timedelta(seconds=30), role="nothing_new")
    _points(catalog, _T0 + timedelta(hours=1), role="standby", session_received_bytes=9_728)
    _points(catalog, round_started_at, round_started_at + timedelta(seconds=30))
    assert set(
        source_point_store.read_earlier_points(_KEY, before=round_started_at, node_id=NodeId("n1"))
    ) == {
        LatestPoint(
            role=SourceRole.NOTHING_NEW,
            observed_at=_T0 + timedelta(seconds=30),
            session_received_bytes=0,
        ),
        LatestPoint(
            role=SourceRole.STANDBY,
            observed_at=_T0 + timedelta(hours=1),
            session_received_bytes=9_728,
        ),
    }


def test_earlier_points_read_this_sources_points_on_every_file_of_the_given_node_only(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    later = _T0 + timedelta(hours=1)
    _points(catalog, _T0, role="sending", native_id=_OTHER_FILE)
    _points(catalog, later, user_hash=_OTHER_USER)
    _points(catalog, later, node_id="n2")
    assert source_point_store.read_earlier_points(
        _KEY, before=later + timedelta(seconds=30), node_id=NodeId("n1")
    ) == (LatestPoint(role=SourceRole.SENDING, observed_at=_T0, session_received_bytes=0),)
    assert (
        source_point_store.read_earlier_points(_OTHER_KEY, before=later, node_id=NodeId("n1")) == ()
    )
    assert source_point_store.read_earlier_points(
        _KEY, before=later + timedelta(seconds=30), node_id=NodeId("n2")
    ) == (LatestPoint(role=SourceRole.QUEUED, observed_at=later, session_received_bytes=0),)


def test_has_points_before_reads_only_the_given_nodes_points_before(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    assert not source_point_store.has_points_before(_T0, node_id=NodeId("n1"))
    _points(catalog, _T0 - timedelta(hours=1), node_id="n2")
    assert not source_point_store.has_points_before(_T0, node_id=NodeId("n1"))
    assert source_point_store.has_points_before(_T0, node_id=NodeId("n2"))
    _points(catalog, _T0, role="standby")
    assert not source_point_store.has_points_before(_T0, node_id=NodeId("n1"))
    assert source_point_store.has_points_before(
        _T0 + timedelta(microseconds=1), node_id=NodeId("n1")
    )


class MeasuredRead(Protocol):
    def __call__(self) -> object: ...


def _steps(connection: sqlite3.Connection, read: MeasuredRead) -> int:
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


def _other_variants(catalog: sqlite3.Connection, numbers: range) -> None:
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
        lambda: source_point_store.read_earlier_points(_KEY, before=before, node_id=NodeId("n1")),
    )
    large = _steps(
        catalog,
        lambda: source_point_store.read_earlier_points(
            _OTHER_KEY, before=before, node_id=NodeId("n1")
        ),
    )
    assert abs(large - small) <= small // 10


def test_earlier_points_seek_this_sources_variants_whatever_the_node_holds(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    _points(catalog, _T0)
    _other_variants(catalog, range(100))
    source_point_store.read_earlier_points(
        _KEY, before=_T0, node_id=NodeId("n1")
    )  # the first call prepares the statement
    small = _steps(
        catalog,
        lambda: source_point_store.read_earlier_points(
            _KEY, before=_T0 + timedelta(hours=1), node_id=NodeId("n1")
        ),
    )
    _other_variants(catalog, range(100, 10_000))
    large = _steps(
        catalog,
        lambda: source_point_store.read_earlier_points(
            _KEY, before=_T0 + timedelta(hours=1), node_id=NodeId("n1")
        ),
    )
    assert abs(large - small) <= small // 10


def test_the_latest_point_seeks_this_sources_variants_whatever_the_node_holds(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    _points(catalog, _T0)
    _other_variants(catalog, range(100))
    since, before = _T0, _T0 + timedelta(seconds=30)
    _latest(source_point_store, _passing(), since, before)  # the first call prepares the statement
    small = _steps(catalog, lambda: _latest(source_point_store, _passing(), since, before))
    _other_variants(catalog, range(100, 10_000))
    large = _steps(catalog, lambda: _latest(source_point_store, _passing(), since, before))
    assert abs(large - small) <= small // 10
