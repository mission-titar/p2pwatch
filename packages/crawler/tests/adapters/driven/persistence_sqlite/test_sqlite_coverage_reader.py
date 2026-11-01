"""TDD tests for the catalog's coverage reader (spec W-D6 / §6)."""

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import closing
from pathlib import Path

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_coverage_reader import SqliteCoverageReader
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import (
    ThreadReadConnections,
)
from tests.contracts.application.ports.driven.coverage_reader_contract import (
    CoverageReaderContract,
)
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    open_catalog,
    open_reader,
)
from tests.support.catalog_rows import insert_decision, insert_file


@pytest.fixture
def connection(catalog_db: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(catalog_db)
    yield catalog
    catalog.close()


@pytest.fixture
def thread_read_connections(catalog_db: Path) -> Iterator[ThreadReadConnections]:
    with ThreadReadConnections(catalog_db, open_reader=open_reader) as thread_read_connections:
        yield thread_read_connections


class TestSqliteCoverageReader(CoverageReaderContract):
    @pytest.fixture
    def observation_writer(self, connection: sqlite3.Connection) -> SqliteObservationStore:
        return SqliteObservationStore(connection)

    @pytest.fixture
    def decision_writer(self, connection: sqlite3.Connection) -> SqliteDecisionStore:
        return SqliteDecisionStore(connection)

    @pytest.fixture
    def reader(self, thread_read_connections: ThreadReadConnections) -> SqliteCoverageReader:
        return SqliteCoverageReader(thread_read_connections)


def _read_target_coverage(catalog_db: Path) -> Mapping[TargetId, tuple[DecisionTier, ...]]:
    with ThreadReadConnections(catalog_db, open_reader=open_reader) as thread_read_connections:
        return SqliteCoverageReader(thread_read_connections).read_target_coverage()


def test_coverage_tie_break_on_id(catalog_db: Path) -> None:
    """Same hash, same decided_at, two different tiers → the larger id wins."""
    h = "b" * 32
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_file(connection, native_id=h, size_bytes=200)
        insert_decision(connection, native_id=h, target_id="062A", tier="catalog")
        insert_decision(connection, native_id=h, target_id="062A", tier="download")
    coverage = _read_target_coverage(catalog_db)
    assert coverage[TargetId("062A")] == (DecisionTier.DOWNLOAD,)
