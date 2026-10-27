import gc
import sqlite3
import warnings
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.errors import MigrationError
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    database_opener,
)

_SOURCES = {"sources", "source_variants", "source_observations"}
_CATALOG_TABLES = {"files", "observation_variants", "observations", "match_decisions"} | _SOURCES
_LOCAL_TABLES = {
    "node_runtime",
    "downloads",
    "backoff_states",
    "reevaluation_state",
}


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def test_open_catalog_creates_the_tables_and_versions_the_schema(tmp_path: Path) -> None:
    connection = database_opener().open_catalog(tmp_path / "catalog.db")
    try:
        assert _table_names(connection) == _CATALOG_TABLES
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 13
    finally:
        connection.close()


def test_open_local_creates_the_tables_and_versions_the_schema(tmp_path: Path) -> None:
    connection = database_opener().open_local(tmp_path / "local.db")
    try:
        assert _table_names(connection) == _LOCAL_TABLES
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 12
    finally:
        connection.close()


def test_a_refused_open_closes_its_connection(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    raw = sqlite3.connect(path, autocommit=True)
    raw.execute("PRAGMA user_version = 99")
    raw.close()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(MigrationError, match="99"):
            database_opener().open_catalog(path)
        # A connection left open warns when it is collected.
        gc.collect()
    assert [w for w in caught if issubclass(w.category, ResourceWarning)] == []


def test_open_local_runs_the_pre_migration_copier_before_migrating(tmp_path: Path) -> None:
    leftover = tmp_path / "local.db.pre-0001.partial"
    leftover.write_bytes(b"a copy a stop interrupted")
    database_opener().open_local(tmp_path / "local.db").close()
    assert not leftover.exists()
