import gc
import sqlite3
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.connection import (
    Migration,
    PendingMigrations,
    apply_migrations,
    connect,
    load_scripts,
    pending_migrations,
    utc_iso,
)
from p2pwatch.adapters.driven.persistence_sqlite.errors import MigrationError, PersistenceError

# PRAGMA temp_store: 1 = FILE (0 = the compile-time default).
_TEMP_STORE_FILE = 1

_NO_TRANSACTION = "-- migration: no-transaction\n"
_COPY_BEFORE = "-- migration: copy-before\n"


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def _migrate(connection: sqlite3.Connection, scripts: tuple[Migration, ...]) -> None:
    apply_migrations(connection, pending_migrations(connection, scripts))


def test_connect_registers_the_variant_functions_before_migrating(tmp_path: Path) -> None:
    probe = "CREATE TABLE probe AS SELECT iso_to_micros('1970-01-01T00:00:00.000001+00:00') AS us;"
    connection = connect(tmp_path / "catalog.db")
    try:
        _migrate(connection, (Migration(1, probe),))
        assert connection.execute("SELECT us FROM probe").fetchone()[0] == 1
    finally:
        connection.close()


def test_in_memory_database_is_refused_because_wal_is_required() -> None:
    # :memory: reports journal_mode='memory' (empirically verified) -> flat refusal.
    with pytest.raises(PersistenceError, match="WAL"):
        connect(":memory:")


def test_unopenable_path_raises_persistence_error(tmp_path: Path) -> None:
    with pytest.raises(PersistenceError):
        connect(tmp_path)  # a directory is not a database


def test_pending_migrations_keeps_the_scripts_above_the_version(tmp_path: Path) -> None:
    scripts = (Migration(1, "A"), Migration(2, "B"), Migration(3, "C"))
    connection = sqlite3.connect(tmp_path / "pending.db", autocommit=True)
    try:
        connection.execute("PRAGMA user_version = 1")
        assert pending_migrations(connection, scripts) == PendingMigrations(1, scripts[1:])
    finally:
        connection.close()


def test_pending_migrations_refuses_a_database_newer_than_the_code(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "newer.db", autocommit=True)
    try:
        connection.execute("PRAGMA user_version = 99")
        with pytest.raises(MigrationError, match="99"):
            pending_migrations(connection, (Migration(1, "A"),))
    finally:
        connection.close()


def test_apply_migrations_with_no_scripts_is_a_noop(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "vide.db", autocommit=True)
    try:
        _migrate(connection, ())
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
    finally:
        connection.close()


def test_migrations_sort_through_temporary_files(tmp_path: Path) -> None:
    """The probe records the ``temp_store`` in force while a migration runs: an in-memory sort
    is unbounded (+697 MB for one index at 11.5M rows), a file-backed one is not."""
    connection = sqlite3.connect(tmp_path / "probe.db", autocommit=True)
    script = (
        "CREATE TABLE probe (temp_store INTEGER);\n"
        "INSERT INTO probe SELECT temp_store FROM pragma_temp_store();"
    )
    try:
        _migrate(connection, (Migration(1, script),))
        assert connection.execute("SELECT temp_store FROM probe").fetchone()[0] == _TEMP_STORE_FILE
    finally:
        connection.close()


def test_temp_store_is_restored_after_migrations(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "restore.db", autocommit=True)
    try:
        before = connection.execute("PRAGMA temp_store").fetchone()[0]
        _migrate(connection, (Migration(1, "CREATE TABLE t (x INTEGER);"),))
        assert connection.execute("PRAGMA temp_store").fetchone()[0] == before
    finally:
        connection.close()


def test_temp_store_is_restored_even_when_a_migration_fails(tmp_path: Path) -> None:
    """``open_catalog``'s caller may catch MigrationError and keep the connection's settings."""
    connection = sqlite3.connect(tmp_path / "restore_fail.db", autocommit=True)
    try:
        before = connection.execute("PRAGMA temp_store").fetchone()[0]
        with pytest.raises(MigrationError):
            _migrate(connection, (Migration(1, "INSERT INTO nonexistent VALUES (1);"),))
        assert connection.execute("PRAGMA temp_store").fetchone()[0] == before
    finally:
        connection.close()


def test_failed_script_is_rolled_back_and_version_unchanged(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "echec.db", autocommit=True)
    bad_script = "CREATE TABLE disparait (x INTEGER);\nINSERT INTO inexistante VALUES (1);"
    try:
        with pytest.raises(MigrationError, match="migration 2"):
            _migrate(
                connection,
                (Migration(1, "CREATE TABLE survit (x INTEGER);"), Migration(2, bad_script)),
            )
        # Migration 1 has ITS OWN transaction (applied); migration 2 is ENTIRELY rolled back.
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert _table_names(connection) == {"survit"}
    finally:
        connection.close()


def test_each_applied_script_logs_one_line_before_it_runs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A long first boot shows which script runs, so a silent wait is not taken for a hang."""
    connection = sqlite3.connect(tmp_path / "log.db", autocommit=True)
    scripts = (
        Migration(1, "CREATE TABLE a (x INTEGER);"),
        Migration(2, "CREATE TABLE b (x INTEGER);"),
    )
    try:
        _migrate(connection, scripts[:1])
        caplog.clear()
        with caplog.at_level("INFO"):
            _migrate(connection, scripts)
        assert caplog.messages == ["migration 2: applying"]
    finally:
        connection.close()


def test_load_scripts_orders_by_name_and_skips_non_sql(tmp_path: Path) -> None:
    (tmp_path / "0002_second.sql").write_text("B", encoding="utf-8")
    (tmp_path / "0001_premier.sql").write_text("A", encoding="utf-8")
    (tmp_path / "README.md").write_text("ignored", encoding="utf-8")
    assert load_scripts(tmp_path) == (Migration(1, "A"), Migration(2, "B"))


def test_load_scripts_rejects_a_non_numeric_prefix(tmp_path: Path) -> None:
    (tmp_path / "abcd_mauvais.sql").write_text("X", encoding="utf-8")
    with pytest.raises(MigrationError, match="abcd_mauvais.sql"):
        load_scripts(tmp_path)


def test_utc_iso_is_fixed_width_and_normalizes_to_utc() -> None:
    # Fixed width (microseconds ALWAYS written) => lexicographic order == chronological.
    paris = timezone(timedelta(hours=2))
    moment = datetime(2026, 6, 11, 14, 0, 0, tzinfo=paris)
    assert utc_iso(moment) == "2026-06-11T12:00:00.000000+00:00"


# --- Hardening (adversarial review post-6c389b1) ---


def test_load_scripts_rejects_duplicate_version_numbers(tmp_path: Path) -> None:
    (tmp_path / "0001_a.sql").write_text("A", encoding="utf-8")
    (tmp_path / "0001_b.sql").write_text("B", encoding="utf-8")
    with pytest.raises(MigrationError, match="increasing"):
        load_scripts(tmp_path)


def test_load_scripts_rejects_non_padded_prefixes_that_misorder(tmp_path: Path) -> None:
    # Lexicographic sort: "10_b.sql" < "2_a.sql" -> versions (10, 2), not increasing.
    (tmp_path / "2_a.sql").write_text("A", encoding="utf-8")
    (tmp_path / "10_b.sql").write_text("B", encoding="utf-8")
    with pytest.raises(MigrationError, match="increasing"):
        load_scripts(tmp_path)


def test_stray_commit_in_a_script_is_detected_before_stamping(tmp_path: Path) -> None:
    # A COMMIT inside a script closes its migration's transaction: detection BEFORE the stamp,
    # version unchanged, NO partial state (the attack script only does COMMIT).
    connection = sqlite3.connect(tmp_path / "commit.db", autocommit=True)
    try:
        with pytest.raises(
            MigrationError, match=r"^migration 2: the script closed its migration's transaction"
        ):
            _migrate(
                connection,
                (Migration(1, "CREATE TABLE survit (x INTEGER);"), Migration(2, "COMMIT;")),
            )
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert _table_names(connection) == {"survit"}
    finally:
        connection.close()


def test_stray_commit_followed_by_a_failure_keeps_the_version_unstamped(tmp_path: Path) -> None:
    # Attack variant 2: a stray COMMIT THEN a statement that fails. The work
    # committed by the stray COMMIT is unrecoverable, but the version MUST NOT
    # be stamped (otherwise the migration would be marked applied even though it failed).
    connection = sqlite3.connect(tmp_path / "commit2.db", autocommit=True)
    script = "CREATE TABLE t (x INTEGER);\nCOMMIT;\nINSERT INTO inexistante VALUES (1);"
    try:
        with pytest.raises(MigrationError, match="migration 1"):
            _migrate(connection, (Migration(1, script),))
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
    finally:
        connection.close()


def test_connect_closes_the_connection_when_configuring_fails(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    path.write_bytes(b"not a database" * 100)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(PersistenceError, match="not a database"):
            connect(path)
        # A connection left open warns when it is collected.
        gc.collect()
    assert [w for w in caught if issubclass(w.category, ResourceWarning)] == []


def test_utc_iso_rejects_a_naive_datetime() -> None:
    with pytest.raises(ValueError, match=r"^utc_iso requires an aware datetime$"):
        utc_iso(datetime(2026, 6, 11, 14, 0, 0))


# --- The no-transaction directive and the restored pragmas (stage 1 spec, D8) ---


def test_load_scripts_reads_the_no_transaction_directive(tmp_path: Path) -> None:
    (tmp_path / "0001_plain.sql").write_text("A", encoding="utf-8")
    (tmp_path / "0002_vacuum.sql").write_text(_NO_TRANSACTION + "VACUUM;", encoding="utf-8")
    assert load_scripts(tmp_path) == (
        Migration(1, "A", transactional=True),
        Migration(2, _NO_TRANSACTION + "VACUUM;", transactional=False),
    )


def test_load_scripts_reads_the_copy_before_directive(tmp_path: Path) -> None:
    (tmp_path / "0001_plain.sql").write_text("A", encoding="utf-8")
    (tmp_path / "0002_drop.sql").write_text(_COPY_BEFORE + "DROP TABLE t;", encoding="utf-8")
    assert load_scripts(tmp_path) == (
        Migration(1, "A", copy_before=False),
        Migration(2, _COPY_BEFORE + "DROP TABLE t;", copy_before=True),
    )


def test_load_scripts_rejects_a_misspelled_copy_before_directive(tmp_path: Path) -> None:
    (tmp_path / "0001_typo.sql").write_text(
        "-- migration: copy-befor\nDROP TABLE t;", encoding="utf-8"
    )
    with pytest.raises(MigrationError, match="0001_typo.sql.*copy-befor'"):
        load_scripts(tmp_path)


def test_load_scripts_rejects_a_misspelled_directive(tmp_path: Path) -> None:
    (tmp_path / "0001_typo.sql").write_text(
        "-- migration: no-transction\nVACUUM;", encoding="utf-8"
    )
    with pytest.raises(MigrationError, match="0001_typo.sql.*no-transction"):
        load_scripts(tmp_path)


def test_vacuum_without_the_directive_fails_inside_its_migration_transaction(
    tmp_path: Path,
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "0001_vacuum.sql").write_text("VACUUM;", encoding="utf-8")
    connection = sqlite3.connect(tmp_path / "vacuum.db", autocommit=True)
    try:
        with pytest.raises(MigrationError, match="cannot VACUUM from within a transaction"):
            _migrate(connection, load_scripts(scripts))
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
    finally:
        connection.close()


def test_vacuum_with_the_directive_runs_and_stamps_its_version(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "0001_table.sql").write_text("CREATE TABLE t (x INTEGER);", encoding="utf-8")
    (scripts / "0002_vacuum.sql").write_text(_NO_TRANSACTION + "VACUUM;", encoding="utf-8")
    connection = sqlite3.connect(tmp_path / "vacuum.db", autocommit=True)
    try:
        _migrate(connection, load_scripts(scripts))
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert not connection.in_transaction
    finally:
        connection.close()


def test_failing_script_with_the_directive_leaves_the_version_unchanged(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "0001_table.sql").write_text("CREATE TABLE t (x INTEGER);", encoding="utf-8")
    (scripts / "0002_broken.sql").write_text(
        _NO_TRANSACTION + "INSERT INTO inexistante VALUES (1);", encoding="utf-8"
    )
    connection = sqlite3.connect(tmp_path / "broken.db", autocommit=True)
    try:
        with pytest.raises(MigrationError, match="migration 2"):
            _migrate(connection, load_scripts(scripts))
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        connection.close()


_LARGE_REWRITE_PRAGMAS = "PRAGMA secure_delete = OFF;\nPRAGMA cache_size = -262144;\n"


def _secure_delete_and_cache_size(connection: sqlite3.Connection) -> tuple[int, int]:
    secure_delete = connection.execute("PRAGMA secure_delete").fetchone()[0]
    cache_size = connection.execute("PRAGMA cache_size").fetchone()[0]
    return secure_delete, cache_size


@pytest.mark.parametrize("transactional", [True, False])
def test_a_script_pragmas_are_restored_after_it(tmp_path: Path, transactional: bool) -> None:
    """``secure_delete = 1`` stands for the image's build, which compiles ``SECURE_DELETE`` in."""
    connection = sqlite3.connect(tmp_path / "pragmas.db", autocommit=True)
    try:
        connection.execute("PRAGMA secure_delete = ON")
        before = _secure_delete_and_cache_size(connection)
        script = _LARGE_REWRITE_PRAGMAS + "CREATE TABLE t (x INTEGER);"
        _migrate(connection, (Migration(1, script, transactional),))
        assert _secure_delete_and_cache_size(connection) == before == (1, -2000)
    finally:
        connection.close()


def test_a_script_pragmas_are_restored_even_when_it_fails(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "pragmas_fail.db", autocommit=True)
    try:
        connection.execute("PRAGMA secure_delete = ON")
        before = _secure_delete_and_cache_size(connection)
        script = _LARGE_REWRITE_PRAGMAS + "INSERT INTO inexistante VALUES (1);"
        with pytest.raises(MigrationError):
            _migrate(connection, (Migration(1, script),))
        assert _secure_delete_and_cache_size(connection) == before
    finally:
        connection.close()


def test_a_fast_secure_delete_is_restored_as_fast(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "fast.db", autocommit=True)
    try:
        connection.execute("PRAGMA secure_delete = FAST")
        _migrate(connection, (Migration(1, _LARGE_REWRITE_PRAGMAS),))
        assert connection.execute("PRAGMA secure_delete").fetchone()[0] == 2
    finally:
        connection.close()
