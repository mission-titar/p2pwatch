import gc
import sqlite3
import warnings
from contextlib import closing
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.errors import MigrationError, PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.migration_scripts import Migration, load_scripts
from tests.support.adapters.driven.persistence_sqlite.older_catalog import (
    open_catalog_at,
    open_local_at,
)
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    database_opener,
    database_opener_setting,
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


def test_open_local_runs_the_pre_migration_copier(tmp_path: Path) -> None:
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


# --- The steps of an open: the connection, the pending scripts, their application ---

# PRAGMA temp_store: 1 = FILE (0 = the compile-time default).
_TEMP_STORE_DEFAULT = 0
_TEMP_STORE_FILE = 1

_NO_TRANSACTION = "-- migration: no-transaction\n"


def _open(path: Path, scripts: tuple[Migration, ...]) -> sqlite3.Connection:
    return database_opener().open(path, scripts)


def _version_and_tables(path: Path) -> tuple[int, set[str]]:
    """What a failed open left in ``path``, read once its connection is closed."""
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute("PRAGMA user_version").fetchone()[0], _table_names(connection)


def test_open_registers_the_variant_functions_before_migrating(tmp_path: Path) -> None:
    probe = "CREATE TABLE probe AS SELECT iso_to_micros('1970-01-01T00:00:00.000001+00:00') AS us;"
    with closing(_open(tmp_path / "catalog.db", (Migration(1, probe),))) as connection:
        assert connection.execute("SELECT us FROM probe").fetchone()[0] == 1


def test_in_memory_database_is_refused_because_wal_is_required() -> None:
    # :memory: reports journal_mode='memory' (empirically verified) -> flat refusal.
    with pytest.raises(PersistenceError, match="WAL"):
        _open(Path(":memory:"), ())


def test_unopenable_path_raises_persistence_error(tmp_path: Path) -> None:
    with pytest.raises(PersistenceError):
        _open(tmp_path, ())  # a directory is not a database


def test_open_applies_the_scripts_above_the_version_only(tmp_path: Path) -> None:
    path = tmp_path / "pending.db"
    with closing(sqlite3.connect(path, autocommit=True)) as raw:
        raw.execute("PRAGMA user_version = 1")
    scripts = (
        Migration(1, "CREATE TABLE a (x INTEGER);"),
        Migration(2, "CREATE TABLE b (x INTEGER);"),
        Migration(3, "CREATE TABLE c (x INTEGER);"),
    )
    _open(path, scripts).close()
    assert _version_and_tables(path) == (3, {"b", "c"})


def test_open_refuses_a_database_newer_than_its_scripts(tmp_path: Path) -> None:
    path = tmp_path / "newer.db"
    with closing(sqlite3.connect(path, autocommit=True)) as raw:
        raw.execute("PRAGMA user_version = 99")
    with pytest.raises(MigrationError, match="99"):
        _open(path, (Migration(1, "A"),))


def test_open_with_no_scripts_migrates_nothing(tmp_path: Path) -> None:
    with closing(_open(tmp_path / "vide.db", ())) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0


def test_migrations_sort_through_temporary_files(tmp_path: Path) -> None:
    """The probe records the ``temp_store`` in force while a migration runs: an in-memory sort
    is unbounded (+697 MB for one index at 11.5M rows), a file-backed one is not."""
    script = (
        "CREATE TABLE probe (temp_store INTEGER);\n"
        "INSERT INTO probe SELECT temp_store FROM pragma_temp_store();"
    )
    with closing(_open(tmp_path / "probe.db", (Migration(1, script),))) as connection:
        assert connection.execute("SELECT temp_store FROM probe").fetchone()[0] == _TEMP_STORE_FILE


def test_temp_store_is_restored_after_migrations(tmp_path: Path) -> None:
    scripts = (Migration(1, "CREATE TABLE t (x INTEGER);"),)
    with closing(_open(tmp_path / "restore.db", scripts)) as connection:
        assert connection.execute("PRAGMA temp_store").fetchone()[0] == _TEMP_STORE_DEFAULT


def test_failed_script_is_rolled_back_and_version_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "echec.db"
    bad_script = "CREATE TABLE disparait (x INTEGER);\nINSERT INTO inexistante VALUES (1);"
    with pytest.raises(MigrationError, match="migration 2"):
        _open(path, (Migration(1, "CREATE TABLE survit (x INTEGER);"), Migration(2, bad_script)))
    # Migration 1 has ITS OWN transaction (applied); migration 2 is ENTIRELY rolled back.
    assert _version_and_tables(path) == (1, {"survit"})


def test_each_applied_script_logs_one_line_before_it_runs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A long first boot shows which script runs, so a silent wait is not taken for a hang."""
    path = tmp_path / "log.db"
    scripts = (
        Migration(1, "CREATE TABLE a (x INTEGER);"),
        Migration(2, "CREATE TABLE b (x INTEGER);"),
    )
    _open(path, scripts[:1]).close()
    caplog.clear()
    with caplog.at_level("INFO"):
        _open(path, scripts).close()
    assert caplog.messages == ["migration 2: applying"]


def test_stray_commit_in_a_script_is_detected_before_stamping(tmp_path: Path) -> None:
    # A COMMIT inside a script closes its migration's transaction: detection BEFORE the stamp,
    # version unchanged, NO partial state (the attack script only does COMMIT).
    path = tmp_path / "commit.db"
    with pytest.raises(
        MigrationError, match=r"^migration 2: the script closed its migration's transaction"
    ):
        _open(path, (Migration(1, "CREATE TABLE survit (x INTEGER);"), Migration(2, "COMMIT;")))
    assert _version_and_tables(path) == (1, {"survit"})


def test_stray_commit_followed_by_a_failure_keeps_the_version_unstamped(tmp_path: Path) -> None:
    # Attack variant 2: a stray COMMIT THEN a statement that fails. The work
    # committed by the stray COMMIT is unrecoverable, but the version MUST NOT
    # be stamped (otherwise the migration would be marked applied even though it failed).
    path = tmp_path / "commit2.db"
    script = "CREATE TABLE t (x INTEGER);\nCOMMIT;\nINSERT INTO inexistante VALUES (1);"
    with pytest.raises(MigrationError, match="migration 1"):
        _open(path, (Migration(1, script),))
    assert _version_and_tables(path)[0] == 0


def test_open_closes_the_connection_when_configuring_fails(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    path.write_bytes(b"not a database" * 100)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(PersistenceError, match="not a database"):
            _open(path, ())
        # A connection left open warns when it is collected.
        gc.collect()
    assert [w for w in caught if issubclass(w.category, ResourceWarning)] == []


def test_vacuum_without_the_directive_fails_inside_its_migration_transaction(
    tmp_path: Path,
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "0001_vacuum.sql").write_text("VACUUM;", encoding="utf-8")
    path = tmp_path / "vacuum.db"
    with pytest.raises(MigrationError, match="cannot VACUUM from within a transaction"):
        _open(path, load_scripts(scripts))
    assert _version_and_tables(path)[0] == 0


def test_vacuum_with_the_directive_runs_and_stamps_its_version(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "0001_table.sql").write_text("CREATE TABLE t (x INTEGER);", encoding="utf-8")
    (scripts / "0002_vacuum.sql").write_text(_NO_TRANSACTION + "VACUUM;", encoding="utf-8")
    with closing(_open(tmp_path / "vacuum.db", load_scripts(scripts))) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert not connection.in_transaction


def test_failing_script_with_the_directive_leaves_the_version_unchanged(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "0001_table.sql").write_text("CREATE TABLE t (x INTEGER);", encoding="utf-8")
    (scripts / "0002_broken.sql").write_text(
        _NO_TRANSACTION + "INSERT INTO inexistante VALUES (1);", encoding="utf-8"
    )
    path = tmp_path / "broken.db"
    with pytest.raises(MigrationError, match="migration 2"):
        _open(path, load_scripts(scripts))
    assert _version_and_tables(path)[0] == 1


_LARGE_REWRITE_PRAGMAS = "PRAGMA secure_delete = OFF;\nPRAGMA cache_size = -262144;\n"


@pytest.mark.parametrize("transactional", [True, False])
def test_a_script_pragmas_are_restored_after_it(tmp_path: Path, transactional: bool) -> None:
    """``secure_delete = 1`` stands for the image's build, which compiles ``SECURE_DELETE`` in."""
    opener = database_opener_setting("PRAGMA secure_delete = ON")
    script = _LARGE_REWRITE_PRAGMAS + "CREATE TABLE t (x INTEGER);"
    scripts = (Migration(1, script, transactional),)
    with closing(opener.open(tmp_path / "pragmas.db", scripts)) as connection:
        assert connection.execute("PRAGMA secure_delete").fetchone()[0] == 1
        assert connection.execute("PRAGMA cache_size").fetchone()[0] == -2000


def test_a_fast_secure_delete_is_restored_as_fast(tmp_path: Path) -> None:
    opener = database_opener_setting("PRAGMA secure_delete = FAST")
    scripts = (Migration(1, _LARGE_REWRITE_PRAGMAS),)
    with closing(opener.open(tmp_path / "fast.db", scripts)) as connection:
        assert connection.execute("PRAGMA secure_delete").fetchone()[0] == 2
