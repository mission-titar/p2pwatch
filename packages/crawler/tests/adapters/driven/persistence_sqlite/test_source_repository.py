"""D4's and D5's reads of a source's history on a real catalog (source points spec, section 7)."""

import dataclasses
import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog
from p2pwatch.adapters.driven.persistence_sqlite.source_repository import SqliteSourceRepository
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.source import SourceKey, SourceReading, SourceRole
from p2pwatch.ports.driven.source_points import EarlierPoints
from p2pwatch_testing.catalog_rows import (
    file_id,
    insert_file,
    insert_source,
    insert_source_point,
    insert_source_variant,
)

_FILE, _OTHER_FILE = "a" * 32, "b" * 32
_USER, _OTHER_USER = "1f2e" * 8, "c" * 32
_KEY, _OTHER_KEY = SourceKey(Network.ED2K, _USER), SourceKey(Network.ED2K, _OTHER_USER)
_T0 = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _us(moment: datetime) -> int:
    return (moment - _EPOCH) // timedelta(microseconds=1)


def _points(
    catalog: sqlite3.Connection,
    *moments: datetime,
    role: str = "queued",
    ed2k_hash: str = _FILE,
    user_hash: str = _USER,
    node_id: str = "n1",
) -> None:
    variant_id = insert_source_variant(catalog, ed2k_hash, user_hash, role=role, node_id=node_id)
    for moment in moments:
        insert_source_point(catalog, variant_id, _us(moment))


@pytest.fixture
def catalog(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_catalog(tmp_path / "catalog.db")
    for ed2k_hash in (_FILE, _OTHER_FILE):
        insert_file(connection, ed2k_hash)
    for user_hash in (_USER, _OTHER_USER):
        insert_source(connection, user_hash)
    yield connection
    connection.close()


@pytest.fixture
def repository(catalog: sqlite3.Connection) -> SqliteSourceRepository:
    return SqliteSourceRepository(catalog, timedelta(seconds=30))


def test_earlier_points_count_neither_the_rounds_points_nor_unknown_ones(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    round_started_at = _T0 + timedelta(hours=3)
    _points(catalog, _T0, _T0 + timedelta(seconds=30), role="nothing_new")
    _points(catalog, _T0 + timedelta(hours=1), role="standby")
    _points(catalog, _T0 + timedelta(hours=2), role="undetermined")
    _points(catalog, round_started_at, round_started_at + timedelta(seconds=30))
    assert repository.read_earlier_points(_KEY, round_started_at, "n1") == EarlierPoints(
        has_useful_point=False, latest_known_at=_T0 + timedelta(seconds=30)
    )


def test_earlier_points_read_this_sources_points_on_every_file_of_the_given_node_only(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    later = _T0 + timedelta(hours=1)
    _points(catalog, _T0, role="sending", ed2k_hash=_OTHER_FILE)
    _points(catalog, later, user_hash=_OTHER_USER)
    _points(catalog, later, node_id="n2")
    assert repository.read_earlier_points(
        _KEY, later + timedelta(seconds=30), "n1"
    ) == EarlierPoints(has_useful_point=True, latest_known_at=_T0)
    assert repository.read_earlier_points(_OTHER_KEY, later, "n1") == EarlierPoints(False, None)
    assert repository.read_earlier_points(
        _KEY, later + timedelta(seconds=30), "n2"
    ) == EarlierPoints(has_useful_point=True, latest_known_at=later)


def test_has_points_before_reads_only_the_given_nodes_points_before(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    assert not repository.has_points_before(_T0, "n1")
    _points(catalog, _T0 - timedelta(hours=1), node_id="n2")
    assert not repository.has_points_before(_T0, "n1")
    assert repository.has_points_before(_T0, "n2")
    _points(catalog, _T0, role="standby")
    assert not repository.has_points_before(_T0, "n1")
    assert repository.has_points_before(_T0 + timedelta(microseconds=1), "n1")


def _steps(connection: sqlite3.Connection, read: Callable[[], object]) -> int:
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
        "INSERT INTO source_variants (file_id, name, role, raw_meta, node_id, content_hash)"
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
            variant_id = insert_source_variant(catalog, _FILE, user, role=role)
            catalog.executemany(
                "INSERT INTO source_observations VALUES (?, ?, 0)",
                ((variant_id, _us(_T0) + n * 300_000_000) for n in range(count // 2)),
            )
    repository = SqliteSourceRepository(catalog, timedelta(seconds=30))
    small = _steps(catalog, lambda: repository.read_earlier_points(_KEY, before, "n1"))
    large = _steps(catalog, lambda: repository.read_earlier_points(_OTHER_KEY, before, "n1"))
    assert abs(large - small) <= small // 10


def test_earlier_points_seek_this_sources_variants_whatever_the_node_holds(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    _points(catalog, _T0)
    _other_variants(catalog, range(100))
    repository.read_earlier_points(_KEY, _T0, "n1")  # the first call prepares the statement
    small = _steps(
        catalog, lambda: repository.read_earlier_points(_KEY, _T0 + timedelta(hours=1), "n1")
    )
    _other_variants(catalog, range(100, 10_000))
    large = _steps(
        catalog, lambda: repository.read_earlier_points(_KEY, _T0 + timedelta(hours=1), "n1")
    )
    assert abs(large - small) <= small // 10


def test_a_passing_state_seeks_this_sources_variants_whatever_the_node_holds(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    file = FileKey(Network.ED2K, _FILE)
    reading = SourceReading(_KEY, "AnimuseeFMR", None, SourceRole.QUEUED, None, None, (), 0)
    passing = dataclasses.replace(reading, role=None)
    repository.record_readings(file, [reading], _T0, "n1")
    _other_variants(catalog, range(100))
    # The first passing call prepares the statements.
    repository.record_readings(file, [passing], _T0 + timedelta(seconds=30), "n1")
    small = _steps(
        catalog,
        lambda: repository.record_readings(file, [passing], _T0 + timedelta(seconds=60), "n1"),
    )
    _other_variants(catalog, range(100, 10_000))
    large = _steps(
        catalog,
        lambda: repository.record_readings(file, [passing], _T0 + timedelta(seconds=90), "n1"),
    )
    assert abs(large - small) <= small // 10
