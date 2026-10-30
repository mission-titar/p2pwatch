"""Shared fixtures for the application tests: real engine + real SQLite stores (spec §8)."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from catalog_matching.domain.engine import MatchingEngine
from catalog_matching.domain.validation import parse_matcher_config, parse_targets
from p2pwatch.adapters.driven.config.yaml_loader import load_yaml
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_catalog_scan_reader import (
    SqliteCatalogScanReader,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_wall_clock import FakeWallClock
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_catalog

_MAX_FILENAME_LENGTH = 4096

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
# Matcher: single source of truth = deployment config. Targets: the §7 subset of the golden
# corpus (matching fixture, distinct from the full prod catalog).
_MATCHER = _REPOSITORY_ROOT / "deploy" / "matcher.yml"
_FIXTURES = _REPOSITORY_ROOT / "packages" / "matching" / "tests" / "fixtures"


@pytest.fixture
def engine() -> MatchingEngine:
    """REAL engine: deployment matcher + golden-corpus targets (shared fixtures)."""
    config = parse_matcher_config(load_yaml(_MATCHER))
    targets = parse_targets(load_yaml(_FIXTURES / "golden_targets.yaml"))
    return MatchingEngine(config, targets=targets, max_filename_length=_MAX_FILENAME_LENGTH)


@pytest.fixture
def catalog_connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_catalog(tmp_path / "catalog.db")
    yield connection
    connection.close()


@pytest.fixture
def observation_store(catalog_connection: sqlite3.Connection) -> SqliteObservationStore:
    return SqliteObservationStore(catalog_connection)


@pytest.fixture
def catalog_scan_reader(catalog_connection: sqlite3.Connection) -> SqliteCatalogScanReader:
    return SqliteCatalogScanReader(catalog_connection)


@pytest.fixture
def decision_store(catalog_connection: sqlite3.Connection) -> SqliteDecisionStore:
    return SqliteDecisionStore(catalog_connection)


@pytest.fixture
def fake_time() -> FakeTime:
    return FakeTime()


@pytest.fixture
def wall_clock(fake_time: FakeTime) -> FakeWallClock:
    return fake_time.wall
