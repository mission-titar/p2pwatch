"""D9's reads of a source's history on a real catalog (stage 4 spec, block 15's criteria)."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.persistence_sqlite.connection import open_catalog
from p2pwatch.adapters.persistence_sqlite.source_repository import SqliteSourceRepository
from p2pwatch.domain.file_key import Network
from p2pwatch.domain.source import SourceKey
from p2pwatch.ports.source_repository import EarlierRanges, SourceRepository
from tests.catalog_rows import (
    insert_file,
    insert_source,
    insert_source_range,
    insert_source_variant,
)

_FILE, _OTHER_FILE = "a" * 32, "b" * 32
_USER, _OTHER_USER = "1f2e" * 8, "c" * 32
_KEY, _OTHER_KEY = SourceKey(Network.ED2K, _USER), SourceKey(Network.ED2K, _OTHER_USER)
_T0 = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _us(moment: datetime) -> int:
    return (moment - _EPOCH) // timedelta(microseconds=1)


def _range(
    catalog: sqlite3.Connection,
    first: datetime,
    last: datetime,
    *,
    role: str = "queued",
    ed2k_hash: str = _FILE,
    user_hash: str = _USER,
    node_id: str = "n1",
) -> None:
    variant_id = insert_source_variant(catalog, ed2k_hash, user_hash, role=role)
    insert_source_range(catalog, variant_id, _us(first), _us(last), node_id=node_id)


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
    return SqliteSourceRepository(catalog, "n1")


def test_earlier_ranges_count_neither_the_rounds_range_nor_an_unknown_one(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    round_started_at = _T0 + timedelta(hours=3)
    _range(catalog, _T0, _T0 + timedelta(seconds=30), role="nothing_new")
    _range(catalog, _T0 + timedelta(hours=1), _T0 + timedelta(hours=1), role="standby")
    _range(catalog, _T0 + timedelta(hours=2), round_started_at, role="undetermined")
    _range(catalog, round_started_at, round_started_at + timedelta(seconds=30))
    assert repository.earlier_ranges(_KEY, round_started_at) == EarlierRanges(
        useful=False, last_known_at=_T0 + timedelta(seconds=30)
    )


def test_earlier_ranges_read_this_sources_ranges_on_every_file_of_this_node_only(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    later = _T0 + timedelta(hours=1)
    _range(catalog, _T0, _T0, role="sending", ed2k_hash=_OTHER_FILE)
    _range(catalog, later, later, user_hash=_OTHER_USER)
    _range(catalog, later, later, node_id="n2")
    assert repository.earlier_ranges(_KEY, later + timedelta(seconds=30)) == EarlierRanges(
        useful=True, last_known_at=_T0
    )
    assert repository.earlier_ranges(_OTHER_KEY, later) == EarlierRanges(False, None)


def test_has_ranges_before_reads_only_this_nodes_ranges_started_before(
    repository: SqliteSourceRepository, catalog: sqlite3.Connection
) -> None:
    assert not repository.has_ranges_before(_T0)
    _range(catalog, _T0 - timedelta(hours=1), _T0, node_id="n2")
    assert not repository.has_ranges_before(_T0)
    _range(catalog, _T0, _T0, role="standby")
    assert not repository.has_ranges_before(_T0)
    assert repository.has_ranges_before(_T0 + timedelta(microseconds=1))


def test_the_adapter_satisfies_the_port(repository: SqliteSourceRepository) -> None:
    port: SourceRepository = repository  # mypy proves the structural satisfaction
    assert port is repository
