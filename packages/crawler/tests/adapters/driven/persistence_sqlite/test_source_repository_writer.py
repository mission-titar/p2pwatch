"""D4's writer on a real catalog (source points spec, block 10's criteria)."""

import dataclasses
import hashlib
import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog
from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.source_repository import SqliteSourcePointStore
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.source import RecordedReading, SourceKey, SourceReading, SourceRole
from tests.support.catalog_rows import insert_file

_FILE, _OTHER_FILE = FileKey(Network.ED2K, "a" * 32), FileKey(Network.ED2K, "b" * 32)
_KEY, _OTHER_KEY = SourceKey(Network.ED2K, "1f2e" * 8), SourceKey(Network.ED2K, "c" * 32)
_T0 = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)
_T0_US = int(_T0.timestamp()) * 1_000_000
_POLL = timedelta(seconds=30)
_TOLERANCE = 3 * _POLL
_MICROSECOND = timedelta(microseconds=1)
_Q, _S, _NN = SourceRole.QUEUED, SourceRole.SENDING, SourceRole.NOTHING_NEW
_ST, _UN = SourceRole.STANDBY, SourceRole.UNDETERMINED


def _reading(
    role: SourceRole | None = _Q, *, counter: int = 0, key: SourceKey | None = _KEY
) -> SourceReading:
    return SourceReading(
        source=key,
        source_name="AnimuseeFMR",
        software="emule 0.50a",
        role=role,
        contact_point=None,
        connectable=None,
        raw_meta=(),
        session_received_bytes=counter,
    )


@pytest.fixture
def catalog(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_catalog(tmp_path / "catalog.db")
    insert_file(connection, _FILE.native_id)
    insert_file(connection, _OTHER_FILE.native_id)
    yield connection
    connection.close()


@pytest.fixture
def source_point_store(catalog: sqlite3.Connection) -> SqliteSourcePointStore:
    return SqliteSourcePointStore(catalog, _POLL)


def _record(
    source_point_store: SqliteSourcePointStore, *readings: SourceReading, step: timedelta = _POLL
) -> list[RecordedReading]:
    """Records each reading alone, ``step`` apart from ``_T0``; every reading recorded."""
    recorded: list[RecordedReading] = []
    for index, reading in enumerate(readings):
        recorded += source_point_store.record_readings(_FILE, [reading], _T0 + index * step, "n1")
    return recorded


def _points(catalog: sqlite3.Connection) -> list[tuple[object, ...]]:
    """``(role, observed_at, session_received_bytes)`` in time order."""
    return catalog.execute(
        "SELECT v.role, o.observed_at, o.session_received_bytes"
        " FROM source_observations AS o JOIN source_variants AS v USING (variant_id)"
        " ORDER BY o.observed_at, v.node_id"
    ).fetchall()


def _variants(catalog: sqlite3.Connection) -> int:
    count: int = catalog.execute("SELECT COUNT(*) FROM source_variants").fetchone()[0]
    return count


def _seconds(seconds: float) -> int:
    return _T0_US + int(seconds * 1_000_000)


def test_three_reads_of_one_source_leave_one_variant_and_three_points(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    recorded = _record(source_point_store, *[_reading(counter=counter) for counter in (5, 5, 9)])
    assert recorded == [RecordedReading(_KEY, "AnimuseeFMR", _Q)] * 3
    assert _variants(catalog) == 1
    assert _points(catalog) == [
        ("queued", _T0_US, 5),
        ("queued", _seconds(30), 5),
        ("queued", _seconds(60), 9),
    ]


def test_a_change_of_role_leaves_two_variants(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    _record(source_point_store, _reading(), _reading(_S), _reading())
    assert _variants(catalog) == 2
    assert [row[0] for row in _points(catalog)] == ["queued", "sending", "queued"]


@pytest.mark.parametrize(
    ("gap", "counter", "carried"),
    [
        (_POLL, 5, _Q),
        (_TOLERANCE, 5, _Q),
        (_TOLERANCE + _MICROSECOND, 5, _UN),
        (_POLL, 4, _UN),
    ],
    ids=["30s", "the-tolerance", "past-the-tolerance", "a-lower-counter"],
)
def test_a_passing_state_carries_the_latest_point_within_the_tolerance_and_its_counter(
    source_point_store: SqliteSourcePointStore,
    catalog: sqlite3.Connection,
    gap: timedelta,
    counter: int,
    carried: SourceRole,
) -> None:
    recorded = _record(
        source_point_store, _reading(counter=5), _reading(None, counter=counter), step=gap
    )
    assert recorded[1].role is carried
    assert _points(catalog)[1] == (carried.value, _T0_US + gap // _MICROSECOND, counter)


@pytest.mark.parametrize(
    ("roles", "recorded"),
    [
        ([_NN, None, _NN], [_NN, _NN, _NN]),
        ([_S, None], [_S, _Q]),
        ([_ST, None], [_ST, _UN]),
        ([_Q, _UN, None], [_Q, _UN, _UN]),
        ([None], [_UN]),
    ],
)
def test_a_passing_state_carries_the_group_of_the_latest_point(
    source_point_store: SqliteSourcePointStore,
    catalog: sqlite3.Connection,
    roles: list[SourceRole | None],
    recorded: list[SourceRole],
) -> None:
    assert [
        r.role for r in _record(source_point_store, *[_reading(role) for role in roles])
    ] == recorded
    assert [row[0] for row in _points(catalog)] == [role.value for role in recorded]


def test_a_reading_with_neither_identity_nor_name_writes_nothing(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    reading = dataclasses.replace(_reading(key=None), source_name=None)
    assert source_point_store.record_readings(_FILE, [reading], _T0, "n1") == ()
    assert (_variants(catalog), _points(catalog)) == (0, [])


def test_the_same_read_written_twice_leaves_the_points_unchanged(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    _record(source_point_store, _reading(counter=5), _reading(None, counter=5))
    points = _points(catalog)
    again = source_point_store.record_readings(
        _FILE, [_reading(None, counter=5)], _T0 + _POLL, "n1"
    )
    assert again == (RecordedReading(_KEY, "AnimuseeFMR", _Q),)
    assert _points(catalog) == points


def test_a_negative_counter_is_refused_not_dropped(
    source_point_store: SqliteSourcePointStore,
) -> None:
    with pytest.raises(PersistenceError, match="CHECK constraint failed") as raised:
        source_point_store.record_readings(_FILE, [_reading(counter=-1)], _T0, "n1")
    assert isinstance(raised.value.__cause__, sqlite3.IntegrityError)


def test_a_clock_stepped_back_writes_its_point_and_carries_only_from_an_earlier_one(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    source_point_store.record_readings(_FILE, [_reading(_NN)], _T0 + _POLL, "n1")
    assert source_point_store.record_readings(_FILE, [_reading(None)], _T0, "n1")[0].role is _UN
    assert _points(catalog) == [("undetermined", _T0_US, 0), ("nothing_new", _seconds(30), 0)]


def test_a_reading_without_identity_carries_only_from_its_name_without_identity(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    other = dataclasses.replace(_reading(None, key=None), source_name="Teammate")
    recorded = _record(
        source_point_store, _reading(_NN), _reading(_S, key=None), _reading(None, key=None)
    )
    recorded += source_point_store.record_readings(_FILE, [other], _T0 + 3 * _POLL, "n1")
    assert [(r.source, r.role) for r in recorded] == [
        (_KEY, _NN),
        (None, _S),
        (None, _Q),
        (None, _UN),
    ]
    assert _variants(catalog) == 4


def test_a_source_on_another_file_or_another_node_carries_nothing(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    source_point_store.record_readings(_OTHER_FILE, [_reading(_S)], _T0, "n1")
    source_point_store.record_readings(_FILE, [_reading(_NN)], _T0, "n2")
    assert (
        source_point_store.record_readings(_FILE, [_reading(None)], _T0 + _POLL, "n1")[0].role
        is _UN
    )


def test_another_nodes_identical_reading_is_its_own_variant(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    source_point_store.record_readings(_FILE, [_reading()], _T0, "n2")
    source_point_store.record_readings(_FILE, [_reading()], _T0, "n1")
    assert _variants(catalog) == 2
    assert len(_points(catalog)) == 2
    node_ids = catalog.execute("SELECT node_id FROM source_variants ORDER BY variant_id")
    assert node_ids.fetchall() == [("n2",), ("n1",)]


def test_the_variant_and_the_source_are_written_as_d2_states(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    reading = dataclasses.replace(
        _reading(),
        contact_point="176.103.48.36:4184",
        connectable=True,
        raw_meta=(("source_origin", "kad"), ("protocol_extensions", ("a", "b"))),
    )
    source_point_store.record_readings(_FILE, [reading], _T0, "n1")
    raw_meta = '{"protocol_extensions": ["a", "b"], "source_origin": "kad"}'
    columns: list[object] = [_FILE.file_id.hex(), _KEY.source_id.hex(), "AnimuseeFMR"]
    columns += ["emule 0.50a", "queued", "176.103.48.36:4184", True, raw_meta, "n1"]
    canonical = json.dumps(columns, ensure_ascii=False, separators=(",", ":")).encode()
    assert catalog.execute(
        "SELECT file_id, source_id, name, software, role, contact_point, connectable,"
        " raw_meta, node_id, content_hash FROM source_variants"
    ).fetchall() == [
        (
            _FILE.file_id,
            _KEY.source_id,
            "AnimuseeFMR",
            "emule 0.50a",
            "queued",
            "176.103.48.36:4184",
            1,
            raw_meta,
            "n1",
            hashlib.blake2b(canonical, digest_size=16).digest(),
        )
    ]
    assert catalog.execute("SELECT * FROM sources").fetchall() == [
        (_KEY.source_id, "ed2k", _KEY.native_id)
    ]


def test_a_contact_point_that_is_not_the_files_networks_writes_nothing(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    bad = dataclasses.replace(_reading(key=_OTHER_KEY), contact_point="server.example:4184")
    with pytest.raises(PersistenceError, match="server.example:4184"):
        source_point_store.record_readings(_FILE, [_reading(), bad], _T0, "n1")
    assert _points(catalog) == []


def test_a_failed_write_rolls_back_the_whole_call(
    source_point_store: SqliteSourcePointStore, catalog: sqlite3.Connection
) -> None:
    unknown = FileKey(Network.ED2K, "d" * 32)
    with pytest.raises(PersistenceError, match="FOREIGN KEY"):
        source_point_store.record_readings(unknown, [_reading()], _T0, "n1")
    assert catalog.execute("SELECT COUNT(*) FROM sources").fetchone() == (0,)
    assert not catalog.in_transaction
