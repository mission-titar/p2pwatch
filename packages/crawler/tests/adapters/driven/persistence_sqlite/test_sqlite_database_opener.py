import gc
import sqlite3
import warnings
from contextlib import closing
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.errors import MigrationError
from tests.support.adapters.driven.persistence_sqlite.older_catalog import (
    open_catalog_at,
    open_local_at,
)
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    database_opener,
    open_catalog,
    open_local,
)
from tests.support.catalog_rows import insert_decision, insert_file

# Canonical 32-char lowercase hex hash (satisfies the CHECK constraint).
_CANONICAL_HASH = "a" * 32
_HASH = "0123456789abcdef0123456789abcdef"
_USER_HASH = "1f" * 16
_INSTANT = "2026-03-01T00:00:00.000000+00:00"
# The support opener's FakeTime starts at 2026-06-12 00:00:00 UTC.
_FAKE_TIME_START = "2026-06-12_00-00-00"

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


def _rows_by_table(path: Path) -> dict[str, list[tuple[object, ...]]]:
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table' ORDER BY name"
            )
        ]
        return {
            table: connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
            for table in tables
        }


def _version(path: Path) -> int:
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as connection:
        version: int = connection.execute("PRAGMA user_version").fetchone()[0]
        return version


def _copy_names(directory: Path) -> list[str]:
    return sorted(file.name for file in directory.iterdir() if ".pre-" in file.name)


def _write_catalog_at_5(path: Path) -> None:
    """A version 5 catalog holding a row in every table 0006 keeps or drops, ranges aside (0006
    refuses them)."""
    with closing(open_catalog_at(path, 5)) as connection:
        connection.execute(f"INSERT INTO files (ed2k_hash, size_bytes) VALUES ('{_HASH}', 100)")
        connection.execute(
            "INSERT INTO file_observations (ed2k_hash, filename, size_bytes, source_count,"
            " complete_source_count, raw_meta, keyword, observed_at, node_id) VALUES"
            f" ('{_HASH}', 'Keroro 062A.avi', 100, 3, 1, '{{}}', 'keroro', '{_INSTANT}', 'n1')"
        )
        connection.execute(f"INSERT INTO sources (user_hash) VALUES ('{_USER_HASH}')")
        connection.execute(
            "INSERT INTO source_observations (user_hash, ed2k_hash, raw_meta, observed_at,"
            f" node_id) VALUES ('{_USER_HASH}', '{_HASH}', '{{}}', '{_INSTANT}', 'n1')"
        )
        connection.execute(
            "INSERT INTO match_decisions (ed2k_hash, target_id, rule_name, tier, decided_at,"
            f" node_id) VALUES ('{_HASH}', '062A', 'rule', 'download', '{_INSTANT}', 'n1')"
        )


def test_a_version_5_catalog_leaves_one_copy_at_version_5_holding_its_rows(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.db"
    _write_catalog_at_5(path)
    rows_before = _rows_by_table(path)

    database_opener().open_catalog(path).close()

    assert _copy_names(tmp_path) == [f"catalog.db.pre-0006.{_FAKE_TIME_START}_UTC"]
    copy = tmp_path / f"catalog.db.pre-0006.{_FAKE_TIME_START}_UTC"
    assert _version(copy) == 5
    assert _rows_by_table(copy) == rows_before
    assert [table for table, rows in rows_before.items() if not rows] == ["file_observation_ranges"]
    assert _version(path) == 13


def test_a_migrated_catalog_opened_again_adds_no_file(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    _write_catalog_at_5(path)
    database_opener().open_catalog(path).close()
    files_before = sorted(tmp_path.iterdir())

    database_opener().open_catalog(path).close()

    assert sorted(tmp_path.iterdir()) == files_before


def test_a_new_catalog_is_not_copied(tmp_path: Path) -> None:
    with closing(database_opener().open_catalog(tmp_path / "catalog.db")):
        names = sorted(file.name for file in tmp_path.iterdir())
    assert names == ["catalog.db", "catalog.db-shm", "catalog.db-wal"]


def test_a_marked_migration_below_an_unmarked_one_is_found(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    open_catalog_at(path, 9).close()

    database_opener().open_catalog(path).close()

    assert _copy_names(tmp_path) == [f"catalog.db.pre-0010.{_FAKE_TIME_START}_UTC"]
    assert _version(tmp_path / f"catalog.db.pre-0010.{_FAKE_TIME_START}_UTC") == 9


def test_a_version_5_local_db_leaves_one_copy_at_version_5(tmp_path: Path) -> None:
    path = tmp_path / "local.db"
    with closing(open_local_at(path, 5)) as connection:
        connection.execute(
            "INSERT INTO downloads (ed2k_hash, target_id, state, queued_at, size_bytes)"
            f" VALUES ('{_HASH}', '062A', 'queued', '{_INSTANT}', 100)"
        )
    rows_before = _rows_by_table(path)

    database_opener().open_local(path).close()

    assert _copy_names(tmp_path) == [f"local.db.pre-0006.{_FAKE_TIME_START}_UTC"]
    copy = tmp_path / f"local.db.pre-0006.{_FAKE_TIME_START}_UTC"
    assert _version(copy) == 5
    assert _rows_by_table(copy) == rows_before


def test_open_catalog_indexes_the_source_variants(tmp_path: Path) -> None:
    connection = open_catalog(tmp_path / "catalog.db")
    try:
        rows = connection.execute(
            "SELECT l.name, i.name FROM pragma_index_list('source_variants') AS l,"
            " pragma_index_info(l.name) AS i WHERE l.origin = 'c' ORDER BY l.name, i.seqno"
        ).fetchall()
        assert rows == [
            ("idx_source_variants_file_source", "file_id"),
            ("idx_source_variants_file_source", "source_id"),
            ("idx_source_variants_name", "name"),
            ("idx_source_variants_node_id", "node_id"),
            ("idx_source_variants_source_id", "source_id"),
        ]
    finally:
        connection.close()


def test_open_applies_wal_and_foreign_keys_and_recursive_triggers_pragmas(tmp_path: Path) -> None:
    connection = open_catalog(tmp_path / "catalog.db")
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA recursive_triggers").fetchone()[0] == 1
    finally:
        connection.close()


def test_open_local_applies_recursive_triggers_pragma(tmp_path: Path) -> None:
    connection = open_local(tmp_path / "local.db")
    try:
        assert connection.execute("PRAGMA recursive_triggers").fetchone()[0] == 1
    finally:
        connection.close()


def test_foreign_keys_are_enforced(tmp_path: Path) -> None:
    connection = open_catalog(tmp_path / "catalog.db")
    try:
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            insert_decision(connection, "absent", "t", "catalog")
    finally:
        connection.close()


def test_reopen_is_idempotent_and_keeps_data(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    first = open_catalog(path)
    insert_file(first, _CANONICAL_HASH, 1)
    first.close()
    second = open_catalog(path)  # versions already applied: NO script replays
    try:
        assert second.execute("PRAGMA user_version").fetchone()[0] == 13
        assert second.execute("SELECT count(*) FROM files").fetchone()[0] == 1
    finally:
        second.close()


def test_insert_or_replace_on_existing_hash_raises_integrity_error(tmp_path: Path) -> None:
    """INSERT OR REPLACE on an existing files row must raise: the append-only trigger fires on
    the implicit DELETE that REPLACE performs, since the open turns recursive_triggers on."""
    connection = open_catalog(tmp_path / "catalog.db")
    try:
        insert_file(connection, _CANONICAL_HASH, 1)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT OR REPLACE INTO files SELECT file_id, network, native_id, 2 FROM files"
            )
    finally:
        connection.close()
