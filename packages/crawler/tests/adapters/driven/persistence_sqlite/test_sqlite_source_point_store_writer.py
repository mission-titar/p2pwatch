"""D4's writer on a real catalog (source points spec, block 10's criteria)."""

import dataclasses
import hashlib
import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_catalog
from tests.support.catalog_rows import insert_file

_FILE = FileKey(network=Network.ED2K, native_id="a" * 32)
_KEY = SourceKey(network=Network.ED2K, native_id="1f2e" * 8)
_T0 = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)
_T0_US = int(_T0.timestamp()) * 1_000_000
_POLL = timedelta(seconds=30)
_NODE_ID = NodeId("n1")
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
    role: SourceRole = _Q, *, counter: int = 0, index: int = 0, node_id: NodeId = _NODE_ID
) -> SourcePoint:
    """A point of ``_FILE`` with its reading's role, ``index`` reads after ``_T0``."""
    return SourcePoint(
        file=_FILE,
        reading=_reading(role, counter=counter),
        role=role,
        observed_at=_T0 + index * _POLL,
        node_id=node_id,
    )


@pytest.fixture
def catalog(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_catalog(tmp_path / "catalog.db")
    insert_file(connection, native_id=_FILE.native_id)
    yield connection
    connection.close()


@pytest.fixture
def source_point_store(catalog: sqlite3.Connection) -> SqliteSourcePointStore:
    return SqliteSourcePointStore(catalog)


def _points(catalog: sqlite3.Connection) -> list[dict[str, Any]]:
    """``role``, ``observed_at_micros`` and ``session_received_bytes`` in time order."""
    return rows(
        catalog,
        sql="SELECT v.role, o.observed_at_micros, o.session_received_bytes"
        " FROM source_observations AS o JOIN source_variants AS v USING (variant_id)"
        " ORDER BY o.observed_at_micros, v.node_id",
    )


def _point_row(role: str, observed_at_micros: int, session_received_bytes: int) -> dict[str, Any]:
    return {
        "role": role,
        "observed_at_micros": observed_at_micros,
        "session_received_bytes": session_received_bytes,
    }


def _variants(catalog: sqlite3.Connection) -> int:
    [count] = rows(catalog, sql="SELECT COUNT(*) AS variant_count FROM source_variants")
    variant_count: int = count["variant_count"]
    return variant_count


def _source_count(catalog: sqlite3.Connection) -> int:
    [count] = rows(catalog, sql="SELECT COUNT(*) AS source_count FROM sources")
    source_count: int = count["source_count"]
    return source_count


def _seconds(seconds: float) -> int:
    return _T0_US + int(seconds * 1_000_000)


def test_three_reads_of_one_source_leave_one_variant_and_three_points(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    points = [_point(counter=counter, index=index) for index, counter in enumerate((5, 5, 9))]
    source_point_store.record_points(points)
    assert _variants(catalog) == 1
    assert _points(catalog) == [
        _point_row("queued", _T0_US, 5),
        _point_row("queued", _seconds(30), 5),
        _point_row("queued", _seconds(60), 9),
    ]


def test_a_change_of_role_leaves_two_variants(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    source_point_store.record_points([_point(), _point(_S, index=1), _point(index=2)])
    assert _variants(catalog) == 2
    assert [point["role"] for point in _points(catalog)] == ["queued", "sending", "queued"]


def test_a_point_is_written_with_its_role_a_carried_one_included(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    source_point_store.record_points(
        [
            SourcePoint(
                file=_FILE, reading=_reading(None), role=_Q, observed_at=_T0, node_id=NodeId("n1")
            )
        ]
    )
    assert _points(catalog) == [_point_row("queued", _T0_US, 0)]


def test_a_point_without_identity_writes_its_variant_and_no_source(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    reading = dataclasses.replace(_reading(), source=None)
    source_point_store.record_points(
        [SourcePoint(file=_FILE, reading=reading, role=_Q, observed_at=_T0, node_id=NodeId("n1"))]
    )
    variants = rows(catalog, sql="SELECT source_id, name FROM source_variants")
    assert variants == [{"source_id": None, "name": "AnimuseeFMR"}]
    assert _source_count(catalog) == 0


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
    assert rows(catalog, sql="SELECT node_id FROM source_variants ORDER BY variant_id") == [
        {"node_id": "n2"},
        {"node_id": "n1"},
    ]


def test_the_variant_and_the_source_are_written_as_d2_states(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    reading = dataclasses.replace(
        _reading(),
        contact_point=ContactPoint(network=Network.ED2K, server="176.103.48.36:4184"),
        connectable=True,
        raw_metadata=(("source_origin", "kad"), ("protocol_extensions", ("a", "b"))),
    )
    source_point_store.record_points(
        [SourcePoint(file=_FILE, reading=reading, role=_Q, observed_at=_T0, node_id=NodeId("n1"))]
    )
    raw_metadata = '{"protocol_extensions": ["a", "b"], "source_origin": "kad"}'
    columns: list[object] = [_FILE.file_id.hex(), _KEY.source_id.hex(), "AnimuseeFMR"]
    columns += ["emule 0.50a", "queued", "176.103.48.36:4184", True, raw_metadata, "n1"]
    canonical = json.dumps(columns, ensure_ascii=False, separators=(",", ":")).encode()
    assert rows(
        catalog,
        sql="SELECT file_id, source_id, name, software, role, contact_point, connectable,"
        " raw_metadata, node_id, content_hash FROM source_variants",
    ) == [
        {
            "file_id": _FILE.file_id,
            "source_id": _KEY.source_id,
            "name": "AnimuseeFMR",
            "software": "emule 0.50a",
            "role": "queued",
            "contact_point": "176.103.48.36:4184",
            "connectable": 1,
            "raw_metadata": raw_metadata,
            "node_id": "n1",
            "content_hash": hashlib.blake2b(canonical, digest_size=16).digest(),
        }
    ]
    assert rows(catalog, sql="SELECT * FROM sources") == [
        {"source_id": _KEY.source_id, "network": "ed2k", "native_id": _KEY.native_id}
    ]


def test_a_failed_write_rolls_back_the_whole_call(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    unknown = FileKey(network=Network.ED2K, native_id="d" * 32)
    with pytest.raises(PersistenceError, match="FOREIGN KEY"):
        source_point_store.record_points(
            [
                SourcePoint(
                    file=unknown, reading=_reading(), role=_Q, observed_at=_T0, node_id=NodeId("n1")
                )
            ]
        )
    assert _source_count(catalog) == 0
    assert not catalog.in_transaction
