"""D5's reads of a source's history on a real catalog (source points spec, block 10's criteria)."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.persistence_sqlite.connection import open_catalog
from p2pwatch.adapters.persistence_sqlite.source_repository import SqliteSourceRepository
from p2pwatch.domain.file_key import Network
from p2pwatch.domain.source import SourceKey
from p2pwatch.ports.source_repository import EarlierPoints, SourceRepository
from tests.catalog_rows import (
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
    return SqliteSourceRepository(catalog, "n1", timedelta(seconds=30))


def test_earlier_points_count_neither_the_rounds_points_nor_unknown_ones(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    round_started_at = _T0 + timedelta(hours=3)
    _points(catalog, _T0, _T0 + timedelta(seconds=30), role="nothing_new")
    _points(catalog, _T0 + timedelta(hours=1), role="standby")
    _points(catalog, _T0 + timedelta(hours=2), role="undetermined")
    _points(catalog, round_started_at, round_started_at + timedelta(seconds=30))
    assert repository.earlier_points(_KEY, round_started_at) == EarlierPoints(
        useful=False, last_known_at=_T0 + timedelta(seconds=30)
    )


def test_earlier_points_read_this_sources_points_on_every_file_of_this_node_only(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    later = _T0 + timedelta(hours=1)
    _points(catalog, _T0, role="sending", ed2k_hash=_OTHER_FILE)
    _points(catalog, later, user_hash=_OTHER_USER)
    _points(catalog, later, node_id="n2")
    assert repository.earlier_points(_KEY, later + timedelta(seconds=30)) == EarlierPoints(
        useful=True, last_known_at=_T0
    )
    assert repository.earlier_points(_OTHER_KEY, later) == EarlierPoints(False, None)


def test_has_points_before_reads_only_this_nodes_points_before(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    assert not repository.has_points_before(_T0)
    _points(catalog, _T0 - timedelta(hours=1), node_id="n2")
    assert not repository.has_points_before(_T0)
    _points(catalog, _T0, role="standby")
    assert not repository.has_points_before(_T0)
    assert repository.has_points_before(_T0 + timedelta(microseconds=1))


def _steps(connection: sqlite3.Connection, source: SourceKey, before: datetime) -> int:
    """The SQLite VM instructions ``earlier_points`` runs."""
    steps = 0

    def count() -> int:
        nonlocal steps
        steps += 1
        return 0

    connection.set_progress_handler(count, 1)
    SqliteSourceRepository(connection, "n1", timedelta(seconds=30)).earlier_points(source, before)
    connection.set_progress_handler(None, 1)
    return steps


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
    small, large = _steps(catalog, _KEY, before), _steps(catalog, _OTHER_KEY, before)
    assert abs(large - small) <= small // 10


def test_the_adapter_satisfies_the_port(repository: SqliteSourceRepository) -> None:
    port: SourceRepository = repository  # mypy proves the structural satisfaction
    assert port is repository
