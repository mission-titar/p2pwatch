"""D4's writer on a real catalog (stage 4 spec, block 17's criteria)."""

import dataclasses
import hashlib
import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.persistence_sqlite.connection import open_catalog
from p2pwatch.adapters.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.persistence_sqlite.source_repository import SqliteSourceRepository
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.source import SourceKey, SourceReading, SourceRole
from p2pwatch.ports.source_repository import OpenedRange
from tests.catalog_rows import insert_file

_FILE, _OTHER_FILE = FileKey(Network.ED2K, "a" * 32), FileKey(Network.ED2K, "b" * 32)
_KEY, _OTHER_KEY = SourceKey(Network.ED2K, "1f2e" * 8), SourceKey(Network.ED2K, "c" * 32)
_T0 = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)
_T0_US = int(_T0.timestamp()) * 1_000_000
_POLL = timedelta(seconds=30)
_TOLERANCE = 3 * _POLL
_Q, _S, _NN = SourceRole.QUEUED, SourceRole.SENDING, SourceRole.NOTHING_NEW
_ST, _UN = SourceRole.STANDBY, SourceRole.UNDETERMINED


def _reading(
    role: SourceRole | None = _Q, *, counter: int = 0, key: SourceKey | None = _KEY
) -> SourceReading:
    return SourceReading(
        key=key,
        name="AnimuseeFMR",
        software="emule 0.50a",
        role=role,
        contact_point=None,
        directly_reachable=None,
        raw_meta=(),
        transfer_counter=counter,
    )


@pytest.fixture
def catalog(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_catalog(tmp_path / "catalog.db")
    insert_file(connection, _FILE.native_id)
    insert_file(connection, _OTHER_FILE.native_id)
    yield connection
    connection.close()


@pytest.fixture
def repository(catalog: sqlite3.Connection) -> SqliteSourceRepository:
    return SqliteSourceRepository(catalog, "n1")


def _record(
    repository: SqliteSourceRepository, *readings: SourceReading, step: timedelta = _POLL
) -> list[OpenedRange]:
    """Records each reading alone, ``step`` apart from ``_T0``; every range opened."""
    opened: list[OpenedRange] = []
    for index, reading in enumerate(readings):
        opened += repository.record_readings(_FILE, [reading], _T0 + index * step, _TOLERANCE)
    return opened


def _ranges(catalog: sqlite3.Connection) -> list[tuple[object, ...]]:
    """``(role, first_seen_at, last_seen_at, received_bytes, transfer_counter)`` in time order."""
    return catalog.execute(
        "SELECT v.role, r.first_seen_at, r.last_seen_at, r.received_bytes, r.transfer_counter"
        " FROM source_ranges AS r JOIN source_variants AS v USING (variant_id)"
        " ORDER BY r.first_seen_at, r.node_id"
    ).fetchall()


def _seconds(seconds: float) -> int:
    return _T0_US + int(seconds * 1_000_000)


@pytest.mark.parametrize("gap", [_POLL, _TOLERANCE])
def test_the_same_variant_within_the_tolerance_extends_the_range(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection, gap: timedelta
) -> None:
    opened = _record(repository, _reading(), _reading(), step=gap)
    assert opened == [OpenedRange(_KEY, "AnimuseeFMR", _Q)]
    assert _ranges(catalog) == [("queued", _T0_US, _T0_US + gap // timedelta(microseconds=1), 0, 0)]


@pytest.mark.parametrize(
    ("second", "gap"),
    [
        (_reading(counter=5), _TOLERANCE + timedelta(microseconds=1)),
        (dataclasses.replace(_reading(counter=5), software="emule 0.70b"), _POLL),
        (_reading(counter=4), _POLL),
    ],
    ids=["past-the-tolerance", "another-variant", "a-lower-counter"],
)
def test_each_condition_of_d4_failing_opens_a_second_range(
    repository: SqliteSourceRepository,
    catalog: sqlite3.Connection,
    second: SourceReading,
    gap: timedelta,
) -> None:
    _record(repository, _reading(counter=5), second, step=gap)
    assert len(_ranges(catalog)) == 2


@pytest.mark.parametrize(
    ("roles", "opened"),
    [
        ([_Q, _S, _Q], [_Q, _S, _Q]),
        ([_NN, None, _NN], [_NN]),
        ([_Q, None, _Q], [_Q]),
        ([_Q, _UN], [_Q, _UN]),
        ([_S, None], [_S, _Q]),
        ([_ST, None], [_ST, _UN]),
        ([None], [_UN]),
    ],
)
def test_a_passing_state_carries_the_group_of_the_latest_range(
    repository: SqliteSourceRepository,
    catalog: sqlite3.Connection,
    roles: list[SourceRole | None],
    opened: list[SourceRole],
) -> None:
    ranges = _record(repository, *[_reading(role) for role in roles])
    assert [opened_range.role for opened_range in ranges] == opened
    assert [row[0] for row in _ranges(catalog)] == opened


@pytest.mark.parametrize(
    ("gap", "counter"), [(_TOLERANCE + timedelta(microseconds=1), 5), (_POLL, 4)]
)
def test_a_passing_state_carries_nothing_from_a_range_it_could_not_extend(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection, gap: timedelta, counter: int
) -> None:
    _record(repository, _reading(_NN, counter=5), _reading(None, counter=counter), step=gap)
    assert [row[0] for row in _ranges(catalog)] == ["nothing_new", "undetermined"]


@pytest.mark.parametrize("read_at", [_T0 + _POLL, _T0])
def test_a_reading_at_or_before_the_latest_range_end_writes_nothing(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection, read_at: datetime
) -> None:
    _record(repository, _reading(), _reading())
    assert repository.record_readings(_FILE, [_reading(_S, counter=9)], read_at, _TOLERANCE) == ()
    assert _ranges(catalog) == [("queued", _T0_US, _seconds(30), 0, 0)]


def test_a_second_reading_of_one_identity_in_one_call_writes_nothing(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    repository.record_readings(_FILE, [_reading(), _reading(_S)], _T0, _TOLERANCE)
    assert [row[0] for row in _ranges(catalog)] == ["queued"]


@pytest.mark.parametrize(("role", "received"), [(_ST, 0), (_S, 250)])
def test_only_a_sending_range_adds_the_counters_growth(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection, role: SourceRole, received: int
) -> None:
    _record(repository, *[_reading(role, counter=counter) for counter in (50, 150, 300)])
    assert _ranges(catalog) == [(role.value, _T0_US, _seconds(60), received, 300)]


def test_a_reading_with_neither_identity_nor_name_writes_nothing(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    reading = dataclasses.replace(_reading(key=None), name=None)
    assert repository.record_readings(_FILE, [reading], _T0, _TOLERANCE) == ()
    assert _ranges(catalog) == []


def test_a_reading_without_identity_extends_only_a_range_of_its_name_without_identity(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    opened = _record(repository, _reading(key=None), _reading(), _reading(key=None))
    assert [opened_range.key for opened_range in opened] == [None, _KEY]
    assert _ranges(catalog) == [
        ("queued", _T0_US, _seconds(60), 0, 0),
        ("queued", _seconds(30), _seconds(30), 0, 0),
    ]


def test_two_sources_without_identity_are_told_apart_by_name(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    other = dataclasses.replace(_reading(key=None), name="Teammate")
    repository.record_readings(_FILE, [_reading(key=None), other], _T0, _TOLERANCE)
    assert len(_ranges(catalog)) == 2


def test_a_source_on_another_file_neither_stops_nor_carries_into_this_files_range(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    repository.record_readings(_OTHER_FILE, [_reading(_S)], _T0, _TOLERANCE)
    opened = _record(repository, _reading(None), _reading(None))
    assert [opened_range.role for opened_range in opened] == [_UN]
    assert sorted(_ranges(catalog)) == [
        ("sending", _T0_US, _T0_US, 0, 0),
        ("undetermined", _T0_US, _seconds(30), 0, 0),
    ]


def test_another_nodes_range_is_never_extended_and_its_variant_is_shared(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    SqliteSourceRepository(catalog, "n2").record_readings(_FILE, [_reading()], _T0, _TOLERANCE)
    _record(repository, _reading(), _reading())
    assert catalog.execute("SELECT COUNT(*) FROM source_variants").fetchone() == (1,)
    assert len(_ranges(catalog)) == 2


def test_the_variant_and_the_source_are_written_as_d3_states(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    reading = dataclasses.replace(
        _reading(),
        contact_point="176.103.48.36:4184",
        directly_reachable=True,
        raw_meta=(("source_origin", "kad"), ("protocol_extensions", ("a", "b"))),
    )
    repository.record_readings(_FILE, [reading], _T0, _TOLERANCE)
    raw_meta = '{"protocol_extensions": ["a", "b"], "source_origin": "kad"}'
    columns: list[object] = [_FILE.file_id.hex(), _KEY.source_id.hex(), "AnimuseeFMR"]
    columns += ["emule 0.50a", "queued", "176.103.48.36:4184", True, raw_meta]
    canonical = json.dumps(columns, ensure_ascii=False, separators=(",", ":")).encode()
    assert catalog.execute(
        "SELECT file_id, source_id, name, software, role, contact_point, directly_reachable,"
        " raw_meta, content_hash FROM source_variants"
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
            hashlib.blake2b(canonical, digest_size=16).digest(),
        )
    ]
    assert catalog.execute("SELECT * FROM sources").fetchall() == [
        (_KEY.source_id, "ed2k", _KEY.native_id)
    ]


def test_a_contact_point_that_is_not_the_files_networks_writes_nothing(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    bad = dataclasses.replace(_reading(key=_OTHER_KEY), contact_point="server.example:4184")
    with pytest.raises(PersistenceError, match="server.example:4184"):
        repository.record_readings(_FILE, [_reading(), bad], _T0, _TOLERANCE)
    assert _ranges(catalog) == []


def test_a_failed_write_rolls_back_the_whole_call(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    unknown = FileKey(Network.ED2K, "d" * 32)
    with pytest.raises(PersistenceError, match="FOREIGN KEY"):
        repository.record_readings(unknown, [_reading()], _T0, _TOLERANCE)
    assert catalog.execute("SELECT COUNT(*) FROM sources").fetchone() == (0,)
    assert not catalog.in_transaction
