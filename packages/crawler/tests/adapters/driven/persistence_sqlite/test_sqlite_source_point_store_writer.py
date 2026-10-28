"""D4's writer on a real catalog (source points spec, block 10's criteria)."""

import dataclasses
import hashlib
import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_source_point_store import (
    SqliteSourcePointStore,
)
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.source import (
    ContactPoint,
    SourceKey,
    SourcePoint,
    SourceReading,
    SourceRole,
)
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_catalog
from tests.support.catalog_rows import insert_file

_FILE = FileKey(Network.ED2K, "a" * 32)
_KEY = SourceKey(Network.ED2K, "1f2e" * 8)
_T0 = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)
_T0_US = int(_T0.timestamp()) * 1_000_000
_POLL = timedelta(seconds=30)
_NODE = NodeId("n1")
_Q, _S = SourceRole.QUEUED, SourceRole.SENDING


def _reading(role: SourceRole | None = _Q, *, counter: int = 0) -> SourceReading:
    return SourceReading(
        source=_KEY,
        source_name="AnimuseeFMR",
        software="emule 0.50a",
        role=role,
        contact_point=None,
        connectable=None,
        raw_metadata=(),
        session_received_bytes=counter,
    )


def _point(
    role: SourceRole = _Q, *, counter: int = 0, index: int = 0, node_id: NodeId = _NODE
) -> SourcePoint:
    """A point of ``_FILE`` with its reading's role, ``index`` reads after ``_T0``."""
    return SourcePoint(_FILE, _reading(role, counter=counter), role, _T0 + index * _POLL, node_id)


@pytest.fixture
def catalog(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_catalog(tmp_path / "catalog.db")
    insert_file(connection, _FILE.native_id)
    yield connection
    connection.close()


@pytest.fixture
def source_point_store(catalog: sqlite3.Connection) -> SqliteSourcePointStore:
    return SqliteSourcePointStore(catalog)


def _points(catalog: sqlite3.Connection) -> list[tuple[object, ...]]:
    """``(role, observed_at_micros, session_received_bytes)`` in time order."""
    return catalog.execute(
        "SELECT v.role, o.observed_at_micros, o.session_received_bytes"
        " FROM source_observations AS o JOIN source_variants AS v USING (variant_id)"
        " ORDER BY o.observed_at_micros, v.node_id"
    ).fetchall()


def _variants(catalog: sqlite3.Connection) -> int:
    count: int = catalog.execute("SELECT COUNT(*) FROM source_variants").fetchone()[0]
    return count


def _seconds(seconds: float) -> int:
    return _T0_US + int(seconds * 1_000_000)


def test_three_reads_of_one_source_leave_one_variant_and_three_points(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    points = [_point(counter=counter, index=index) for index, counter in enumerate((5, 5, 9))]
    source_point_store.record_points(points)
    assert _variants(catalog) == 1
    assert _points(catalog) == [
        ("queued", _T0_US, 5),
        ("queued", _seconds(30), 5),
        ("queued", _seconds(60), 9),
    ]


def test_a_change_of_role_leaves_two_variants(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    source_point_store.record_points([_point(), _point(_S, index=1), _point(index=2)])
    assert _variants(catalog) == 2
    assert [row[0] for row in _points(catalog)] == ["queued", "sending", "queued"]


def test_a_point_is_written_with_its_role_a_carried_one_included(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    source_point_store.record_points([SourcePoint(_FILE, _reading(None), _Q, _T0, NodeId("n1"))])
    assert _points(catalog) == [("queued", _T0_US, 0)]


def test_a_point_without_identity_writes_its_variant_and_no_source(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    reading = dataclasses.replace(_reading(), source=None)
    source_point_store.record_points([SourcePoint(_FILE, reading, _Q, _T0, NodeId("n1"))])
    variants = catalog.execute("SELECT source_id, name FROM source_variants").fetchall()
    assert variants == [(None, "AnimuseeFMR")]
    assert catalog.execute("SELECT COUNT(*) FROM sources").fetchone() == (0,)


def test_the_same_read_written_twice_leaves_the_points_unchanged(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    source_point_store.record_points([_point(counter=5), _point(counter=5, index=1)])
    points = _points(catalog)
    source_point_store.record_points([_point(counter=5, index=1)])
    assert _points(catalog) == points


def test_a_negative_counter_is_refused_not_dropped(
    source_point_store: SqliteSourcePointStore,
) -> None:
    with pytest.raises(PersistenceError, match="CHECK constraint failed") as raised:
        source_point_store.record_points([_point(counter=-1)])
    assert isinstance(raised.value.__cause__, sqlite3.IntegrityError)


def test_another_nodes_identical_reading_is_its_own_variant(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    source_point_store.record_points([_point(node_id=NodeId("n2")), _point()])
    assert _variants(catalog) == 2
    assert len(_points(catalog)) == 2
    node_ids = catalog.execute("SELECT node_id FROM source_variants ORDER BY variant_id")
    assert node_ids.fetchall() == [("n2",), ("n1",)]


def test_the_variant_and_the_source_are_written_as_d2_states(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    reading = dataclasses.replace(
        _reading(),
        contact_point=ContactPoint(Network.ED2K, "176.103.48.36:4184"),
        connectable=True,
        raw_metadata=(("source_origin", "kad"), ("protocol_extensions", ("a", "b"))),
    )
    source_point_store.record_points([SourcePoint(_FILE, reading, _Q, _T0, NodeId("n1"))])
    raw_metadata = '{"protocol_extensions": ["a", "b"], "source_origin": "kad"}'
    columns: list[object] = [_FILE.file_id.hex(), _KEY.source_id.hex(), "AnimuseeFMR"]
    columns += ["emule 0.50a", "queued", "176.103.48.36:4184", True, raw_metadata, "n1"]
    canonical = json.dumps(columns, ensure_ascii=False, separators=(",", ":")).encode()
    assert catalog.execute(
        "SELECT file_id, source_id, name, software, role, contact_point, connectable,"
        " raw_metadata, node_id, content_hash FROM source_variants"
    ).fetchall() == [
        (
            _FILE.file_id,
            _KEY.source_id,
            "AnimuseeFMR",
            "emule 0.50a",
            "queued",
            "176.103.48.36:4184",
            1,
            raw_metadata,
            "n1",
            hashlib.blake2b(canonical, digest_size=16).digest(),
        )
    ]
    assert catalog.execute("SELECT * FROM sources").fetchall() == [
        (_KEY.source_id, "ed2k", _KEY.native_id)
    ]


def test_a_failed_write_rolls_back_the_whole_call(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    unknown = FileKey(Network.ED2K, "d" * 32)
    with pytest.raises(PersistenceError, match="FOREIGN KEY"):
        source_point_store.record_points([SourcePoint(unknown, _reading(), _Q, _T0, NodeId("n1"))])
    assert catalog.execute("SELECT COUNT(*) FROM sources").fetchone() == (0,)
    assert not catalog.in_transaction
