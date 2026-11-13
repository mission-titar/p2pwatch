import gc
import re
import sqlite3
import warnings
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from p2pwatch.adapters.driven.persistence_sqlite import observation_read
from p2pwatch.adapters.driven.persistence_sqlite.errors import (
    MigrationError,
    OpeningInterruptedError,
    PersistenceError,
)
from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from p2pwatch.adapters.driven.persistence_sqlite.migration_scripts import Migration, load_scripts
from p2pwatch.adapters.driven.persistence_sqlite.named_row import NamedRow
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import read_only_uri
from p2pwatch.adapters.driven.shutil_free_space_meter import ShutilFreeSpaceMeter
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.gigabytes import gigabytes
from p2pwatch.domain.out_of_space_error import OutOfSpaceError
from tests.fakes.adapters.driven.fake_free_bytes import FakeFreeBytes
from tests.fakes.adapters.driven.fake_memory_releaser import FakeMemoryReleaser
from tests.fakes.adapters.driven.fake_ticker import FakeTicker
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import (
    open_catalog_at,
    open_local_at,
)
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    ShutdownFlag,
    database_opener,
    database_opener_preparing,
    database_opener_registering,
    database_opener_setting,
    database_opener_ticked_by,
    database_opener_ticked_by_progress,
    database_opener_with_shutdown,
    open_catalog,
    open_local,
)
from tests.support.catalog_rows import insert_decision, insert_file

# Canonical 32-char lowercase hex hash (satisfies the CHECK constraint).
_CANONICAL_HASH = "a" * 32
_HASH = "0123456789abcdef0123456789abcdef"
_USER_HASH = "1f" * 16
_INSTANT = "2026-03-01T00:00:00.000000+00:00"
_LATEST_V4_INSTANT = "2026-10-28T21:43:14.401885+00:00"
# The support opener's FakeTime starts at 2026-06-12 00:00:00 UTC.
_FAKE_TIME_START = "2026-06-12_00-00-00"

_SOURCES = {"sources", "source_variants", "source_observations"}
_CATALOG_TABLES = {"files", "observation_variants", "observations", "match_decisions"} | _SOURCES
_LOCAL_TABLES = {
    "node_identity",
    "downloads",
    "backoff_states",
    "latest_search_starts",
    "reevaluation_state",
}


def _table_names(connection: sqlite3.Connection) -> set[str]:
    tables = rows(
        connection,
        sql="SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'",
    )
    return {table["name"] for table in tables}


def _strict_by_table(connection: sqlite3.Connection) -> dict[str, int]:
    tables = rows(
        connection,
        sql="SELECT name, strict FROM pragma_table_list"
        " WHERE schema = 'main' AND name NOT LIKE 'sqlite_%'",
    )
    return {table["name"]: table["strict"] for table in tables}


def test_open_catalog_creates_the_tables_and_versions_the_schema(tmp_path: Path) -> None:
    connection = database_opener().open_catalog(tmp_path / "catalog.db")
    try:
        assert _table_names(connection) == _CATALOG_TABLES
        assert rows(connection, sql="PRAGMA user_version") == [{"user_version": 15}]
    finally:
        connection.close()


def test_open_catalog_makes_every_table_strict(tmp_path: Path) -> None:
    with closing(database_opener().open_catalog(tmp_path / "catalog.db")) as connection:
        assert _strict_by_table(connection) == dict.fromkeys(_CATALOG_TABLES, 1)


def test_open_catalog_keeps_a_file_s_size_in_files_alone(tmp_path: Path) -> None:
    with closing(database_opener().open_catalog(tmp_path / "catalog.db")) as connection:
        sized = rows(
            connection,
            sql="SELECT t.name AS table_name"
            " FROM sqlite_schema AS t, pragma_table_info(t.name) AS c"
            " WHERE t.type = 'table' AND c.name = 'size_bytes'",
        )
    assert sized == [{"table_name": "files"}]


def test_open_local_creates_the_tables_and_versions_the_schema(tmp_path: Path) -> None:
    connection = database_opener().open_local(tmp_path / "local.db")
    try:
        assert _table_names(connection) == _LOCAL_TABLES
        assert rows(connection, sql="PRAGMA user_version") == [{"user_version": 16}]
    finally:
        connection.close()


def test_open_catalog_returns_rows_read_by_column_name(tmp_path: Path) -> None:
    with closing(database_opener().open_catalog(tmp_path / "catalog.db")) as connection:
        row = connection.execute("SELECT 1 AS file_id").fetchone()
    assert isinstance(row, NamedRow)
    assert row == {"file_id": 1}


def test_open_local_returns_rows_read_by_column_name(tmp_path: Path) -> None:
    with closing(database_opener().open_local(tmp_path / "local.db")) as connection:
        row = connection.execute("SELECT 1 AS node_id").fetchone()
    assert isinstance(row, NamedRow)
    assert row == {"node_id": 1}


def test_open_local_refuses_a_column_name_that_appears_twice(tmp_path: Path) -> None:
    with (
        closing(database_opener().open_local(tmp_path / "local.db")) as connection,
        pytest.raises(ValueError, match="'a' appears twice"),
    ):
        connection.execute("SELECT 1 AS a, 2 AS b, 3 AS a").fetchone()


def _seeded_catalog(path: Path) -> Path:
    with closing(open_catalog(path)) as writer:
        insert_file(writer, native_id=_CANONICAL_HASH, size_bytes=10)
    return path


def test_open_reader_returns_rows_read_by_column_name(tmp_path: Path) -> None:
    path = _seeded_catalog(tmp_path / "catalog.db")
    with closing(database_opener().open_reader(path)) as reader:
        row = reader.execute("SELECT native_id, size_bytes FROM files").fetchone()
    assert isinstance(row, NamedRow)
    assert row == {"native_id": _CANONICAL_HASH, "size_bytes": 10}


def test_open_reader_refuses_a_column_name_that_appears_twice(tmp_path: Path) -> None:
    path = _seeded_catalog(tmp_path / "catalog.db")
    with (
        closing(database_opener().open_reader(path)) as reader,
        pytest.raises(ValueError, match="'a' appears twice"),
    ):
        reader.execute("SELECT 1 AS a, 2 AS a").fetchone()


def test_open_in_memory_attaches_a_catalog_and_reads_its_rows_by_column_name(
    tmp_path: Path,
) -> None:
    path = _seeded_catalog(tmp_path / "catalog.db")
    with closing(database_opener().open_in_memory()) as connection:
        connection.execute("ATTACH DATABASE ? AS attached", (str(path),))
        row = connection.execute("SELECT native_id FROM attached.files").fetchone()
        main_files = rows(connection, sql="SELECT file FROM pragma_database_list WHERE seq = 0")
    assert isinstance(row, NamedRow)
    assert row == {"native_id": _CANONICAL_HASH}
    assert main_files == [{"file": ""}]


@pytest.mark.parametrize("in_memory", [True, False], ids=["in_memory", "catalog"])
def test_a_connection_attaches_a_database_read_only_by_its_uri(
    *, tmp_path: Path, in_memory: bool
) -> None:
    directory = tmp_path / "data #%?"
    directory.mkdir()
    path = _seeded_catalog(directory / "catalog.db")
    connection = (
        database_opener().open_in_memory() if in_memory else open_catalog(tmp_path / "other.db")
    )
    with closing(connection):
        connection.execute("ATTACH DATABASE ? AS attached", (read_only_uri(path),))
        attached_files = rows(connection, sql="SELECT native_id FROM attached.files")
        with pytest.raises(sqlite3.OperationalError, match="readonly database"):
            connection.execute("DELETE FROM attached.files")
    assert attached_files == [{"native_id": _CANONICAL_HASH}]


def test_catalog_version_is_the_one_open_catalog_brings_a_catalog_to(tmp_path: Path) -> None:
    with closing(open_catalog(tmp_path / "catalog.db")) as connection:
        [written] = rows(connection, sql="PRAGMA user_version")
    assert database_opener().catalog_version() == written["user_version"]


def test_open_reader_refuses_writes(tmp_path: Path) -> None:
    """``mode=ro`` + ``query_only`` is a double guard: an INSERT raises ``OperationalError``."""
    path = _seeded_catalog(tmp_path / "catalog.db")
    with (
        closing(database_opener().open_reader(path)) as reader,
        pytest.raises(sqlite3.OperationalError),
    ):
        insert_file(reader, native_id=_HASH, size_bytes=1)


def test_open_reader_sorts_through_temporary_files(tmp_path: Path) -> None:
    """``temp_store=FILE`` (1), as the opener sets it to migrate: an in-memory sort is unbounded
    (stage 1, D8)."""
    path = _seeded_catalog(tmp_path / "catalog.db")
    with closing(database_opener().open_reader(path)) as reader:
        assert rows(reader, sql="PRAGMA temp_store") == [{"temp_store": 1}]


def test_open_reader_folds_a_search_text(tmp_path: Path) -> None:
    path = _seeded_catalog(tmp_path / "catalog.db")
    with closing(database_opener().open_reader(path)) as reader:
        assert rows(reader, sql="SELECT fold_for_search('ÉCOLE') AS folded") == [
            {"folded": "ecole"}
        ]


def test_open_reader_refuses_use_from_another_thread(tmp_path: Path) -> None:
    path = _seeded_catalog(tmp_path / "catalog.db")
    with closing(database_opener().open_reader(path)) as reader:
        with ThreadPoolExecutor(max_workers=1) as executor:
            query = executor.submit(reader.execute, "SELECT 1")
        with pytest.raises(sqlite3.ProgrammingError, match="same thread"):
            query.result()


def test_open_reader_opens_a_path_holding_characters_a_uri_escapes(tmp_path: Path) -> None:
    directory = tmp_path / "data #%?"
    directory.mkdir()
    path = _seeded_catalog(directory / "catalog.db")
    with closing(database_opener().open_reader(path)) as reader:
        assert rows(reader, sql="SELECT native_id FROM files") == [{"native_id": _CANONICAL_HASH}]


def test_open_reader_of_a_missing_file_raises_persistence_error(tmp_path: Path) -> None:
    with pytest.raises(PersistenceError, match="unable to open database file"):
        database_opener().open_reader(tmp_path / "catalog.db")


def test_open_catalog_opens_a_path_holding_characters_a_uri_escapes(tmp_path: Path) -> None:
    directory = tmp_path / "data #%?"
    directory.mkdir()
    path = _seeded_catalog(directory / "catalog.db")
    assert sorted(child.name for child in directory.iterdir()) == ["catalog.db"]
    with closing(open_catalog(path)) as connection:
        assert rows(connection, sql="SELECT native_id FROM files") == [
            {"native_id": _CANONICAL_HASH}
        ]


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


def _rows_by_table(path: Path) -> dict[str, list[dict[str, Any]]]:
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as connection:
        tables = [
            row["name"]
            for row in rows(
                connection, sql="SELECT name FROM sqlite_schema WHERE type = 'table' ORDER BY name"
            )
        ]
        return {
            table: rows(connection, sql=f'SELECT * FROM "{table}" ORDER BY rowid')
            for table in tables
        }


def _version(path: Path) -> int:
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as connection:
        (row,) = rows(connection, sql="PRAGMA user_version")
        version: int = row["user_version"]
        return version


def _copy_names(directory: Path) -> list[str]:
    return sorted(file.name for file in directory.iterdir() if ".pre-" in file.name)


def _write_catalog_at_5(path: Path) -> None:
    """A version 5 catalog holding a row in every table 0006 keeps or drops, ranges aside (0006
    refuses them), at the extremes of the operator's v4 catalog."""
    with closing(open_catalog_at(path, version=5)) as connection:
        connection.executemany(
            "INSERT INTO files (ed2k_hash, size_bytes) VALUES (?, ?)",
            [(_HASH, 196), (_CANONICAL_HASH, 28_737_952_534)],
        )
        connection.executemany(
            "INSERT INTO file_observations (ed2k_hash, filename, size_bytes, source_count,"
            " complete_source_count, media_length_sec, bitrate_kbps, raw_meta, keyword,"
            " observed_at, node_id) VALUES (?, 'Keroro 062A.avi', ?, ?, 1, ?, ?, '{}', 'keroro',"
            " ?, 'n1')",
            [
                (_HASH, 196, 0, 32, 0, "2026-07-04T04:30:19.228441+00:00"),
                (_CANONICAL_HASH, 28_737_952_534, 12, 3576, 4498, _LATEST_V4_INSTANT),
            ],
        )
        connection.execute(f"INSERT INTO sources (user_hash) VALUES ('{_USER_HASH}')")
        connection.execute(
            "INSERT INTO source_observations (user_hash, ed2k_hash, raw_meta, observed_at,"
            f" node_id) VALUES ('{_USER_HASH}', '{_HASH}', '{{}}', '{_INSTANT}', 'n1')"
        )
        connection.executemany(
            "INSERT INTO match_decisions (ed2k_hash, target_id, rule_name, tier, decided_at,"
            f" node_id) VALUES ('{_HASH}', ?, 'rule', ?, '{_INSTANT}', 'n1')",
            [("062A", "catalog"), ("062A", "notify"), ("062A", "download"), ("", "retracted")],
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
    assert [table for table, table_rows in rows_before.items() if not table_rows] == [
        "file_observation_ranges"
    ]
    assert _version(path) == 15


def test_a_version_5_catalog_migrates_into_strict_tables_its_quick_check_ok(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.db"
    _write_catalog_at_5(path)

    with closing(database_opener().open_catalog(path)) as connection:
        assert rows(connection, sql="PRAGMA user_version") == [{"user_version": 15}]
        assert _strict_by_table(connection) == dict.fromkeys(_CATALOG_TABLES, 1)
        assert rows(connection, sql="PRAGMA quick_check") == [{"quick_check": "ok"}]
        assert rows(
            connection,
            sql="SELECT (SELECT count(*) FROM observations) AS observation_count,"
            " (SELECT count(*) FROM match_decisions) AS decision_count",
        ) == [{"observation_count": 2, "decision_count": 4}]


def test_a_version_5_file_reported_at_two_sizes_migrates_into_one_variant_read_at_its_size(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.db"
    with closing(open_catalog_at(path, version=5)) as connection:
        connection.execute(f"INSERT INTO files (ed2k_hash, size_bytes) VALUES ('{_HASH}', 100)")
        connection.executemany(
            "INSERT INTO file_observations (ed2k_hash, filename, size_bytes, source_count,"
            " complete_source_count, raw_meta, keyword, observed_at, node_id)"
            f" VALUES ('{_HASH}', 'Keroro 062A.avi', ?, 1, 0, '[]', 'keroro', ?, 'n1')",
            [(100, _INSTANT), (101, _LATEST_V4_INSTANT)],
        )

    with closing(database_opener().open_catalog(path)) as connection:
        assert rows(
            connection, sql="SELECT count(*) AS variant_count FROM observation_variants"
        ) == [{"variant_count": 1}]
        timeline = observation_read.observations_between(
            connection,
            file=FileKey(network=Network.ED2K, native_id=_HASH),
            since=0,
            until=instant_to_micros(datetime.fromisoformat(_LATEST_V4_INSTANT)) + 1,
        )
    assert [observation.reported_file.size_bytes for observation in timeline] == [100, 100]


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
    open_catalog_at(path, version=9).close()

    database_opener().open_catalog(path).close()

    assert _copy_names(tmp_path) == [f"catalog.db.pre-0010.{_FAKE_TIME_START}_UTC"]
    assert _version(tmp_path / f"catalog.db.pre-0010.{_FAKE_TIME_START}_UTC") == 9


def test_a_version_5_local_db_leaves_one_copy_at_version_5(tmp_path: Path) -> None:
    path = tmp_path / "local.db"
    with closing(open_local_at(path, version=5)) as connection:
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
        indexed_columns = rows(
            connection,
            sql="SELECT l.name AS index_name, i.name AS column_name"
            " FROM pragma_index_list('source_variants') AS l, pragma_index_info(l.name) AS i"
            " WHERE l.origin = 'c' ORDER BY l.name, i.seqno",
        )
        assert indexed_columns == [
            {"index_name": index_name, "column_name": column_name}
            for index_name, column_name in (
                ("idx_source_variants_file_source", "file_id"),
                ("idx_source_variants_file_source", "source_id"),
                ("idx_source_variants_name", "name"),
                ("idx_source_variants_node_id", "node_id"),
                ("idx_source_variants_source_id", "source_id"),
            )
        ]
    finally:
        connection.close()


def test_open_applies_wal_and_foreign_keys_and_recursive_triggers_pragmas(tmp_path: Path) -> None:
    connection = open_catalog(tmp_path / "catalog.db")
    try:
        assert rows(connection, sql="PRAGMA journal_mode") == [{"journal_mode": "wal"}]
        assert rows(connection, sql="PRAGMA foreign_keys") == [{"foreign_keys": 1}]
        assert rows(connection, sql="PRAGMA recursive_triggers") == [{"recursive_triggers": 1}]
    finally:
        connection.close()


def test_open_local_applies_recursive_triggers_pragma(tmp_path: Path) -> None:
    connection = open_local(tmp_path / "local.db")
    try:
        assert rows(connection, sql="PRAGMA recursive_triggers") == [{"recursive_triggers": 1}]
    finally:
        connection.close()


def test_foreign_keys_are_enforced(tmp_path: Path) -> None:
    connection = open_catalog(tmp_path / "catalog.db")
    try:
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            insert_decision(connection, native_id="absent", target_id="t", tier="catalog")
    finally:
        connection.close()


def test_reopen_is_idempotent_and_keeps_data(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    first = open_catalog(path)
    insert_file(first, native_id=_CANONICAL_HASH, size_bytes=1)
    first.close()
    second = open_catalog(path)  # versions already applied: NO script replays
    try:
        assert rows(second, sql="PRAGMA user_version") == [{"user_version": 15}]
        assert rows(second, sql="SELECT count(*) AS file_count FROM files") == [{"file_count": 1}]
    finally:
        second.close()


def test_insert_or_replace_on_existing_hash_raises_integrity_error(tmp_path: Path) -> None:
    """INSERT OR REPLACE on an existing files row must raise: the append-only trigger fires on
    the implicit DELETE that REPLACE performs, since the open turns recursive_triggers on."""
    connection = open_catalog(tmp_path / "catalog.db")
    try:
        insert_file(connection, native_id=_CANONICAL_HASH, size_bytes=1)
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


def _open(path: Path, *, scripts: tuple[Migration, ...]) -> sqlite3.Connection:
    return database_opener().open(path, scripts=scripts)


def _version_and_tables(path: Path) -> tuple[int, set[str]]:
    """What a failed open left in ``path``, read once its connection is closed."""
    with closing(sqlite3.connect(path)) as connection:
        (row,) = rows(connection, sql="PRAGMA user_version")
        return row["user_version"], _table_names(connection)


def test_open_registers_the_variant_functions_before_migrating(tmp_path: Path) -> None:
    probe = "CREATE TABLE probe AS SELECT iso_to_micros('1970-01-01T00:00:00.000001+00:00') AS us;"
    with closing(
        _open(tmp_path / "catalog.db", scripts=(Migration(version=1, script=probe),))
    ) as connection:
        assert rows(connection, sql="SELECT us FROM probe") == [{"us": 1}]


@pytest.mark.parametrize(
    "scripts",
    [(), (Migration(version=1, script="CREATE TABLE t (x);"),)],
    ids=["nothing pending", "reopened after a block"],
)
def test_open_removes_iso_to_micros_once_migrated(
    *, tmp_path: Path, scripts: tuple[Migration, ...]
) -> None:
    with (
        closing(_open(tmp_path / "catalog.db", scripts=scripts)) as connection,
        pytest.raises(sqlite3.OperationalError, match="no such function: iso_to_micros"),
    ):
        connection.execute("SELECT iso_to_micros('1970-01-01T00:00:00.000001+00:00')")


def test_in_memory_database_is_refused_because_wal_is_required() -> None:
    # :memory: reports journal_mode='memory' (empirically verified) -> flat refusal.
    with pytest.raises(PersistenceError, match="WAL"):
        _open(Path(":memory:"), scripts=())


def test_unopenable_path_raises_persistence_error(tmp_path: Path) -> None:
    with pytest.raises(PersistenceError):
        _open(tmp_path, scripts=())  # a directory is not a database


def test_open_applies_the_scripts_above_the_version_only(tmp_path: Path) -> None:
    path = tmp_path / "pending.db"
    with closing(sqlite3.connect(path, autocommit=True)) as raw:
        raw.execute("PRAGMA user_version = 1")
    scripts = (
        Migration(version=1, script="CREATE TABLE a (x INTEGER);"),
        Migration(version=2, script="CREATE TABLE b (x INTEGER);"),
        Migration(version=3, script="CREATE TABLE c (x INTEGER);"),
    )
    _open(path, scripts=scripts).close()
    assert _version_and_tables(path) == (3, {"b", "c"})


def test_open_refuses_a_database_newer_than_its_scripts(tmp_path: Path) -> None:
    path = tmp_path / "newer.db"
    with closing(sqlite3.connect(path, autocommit=True)) as raw:
        raw.execute("PRAGMA user_version = 99")
    with pytest.raises(MigrationError, match="99"):
        _open(path, scripts=(Migration(version=1, script="A"),))


def test_open_with_no_scripts_migrates_nothing(tmp_path: Path) -> None:
    with closing(_open(tmp_path / "vide.db", scripts=())) as connection:
        assert rows(connection, sql="PRAGMA user_version") == [{"user_version": 0}]


def test_migrations_sort_through_temporary_files(tmp_path: Path) -> None:
    """The probe records the ``temp_store`` in force while a migration runs: an in-memory sort
    is unbounded (+697 MB for one index at 11.5M rows), a file-backed one is not."""
    script = (
        "CREATE TABLE probe (temp_store INTEGER);\n"
        "INSERT INTO probe SELECT temp_store FROM pragma_temp_store();"
    )
    with closing(
        _open(tmp_path / "probe.db", scripts=(Migration(version=1, script=script),))
    ) as connection:
        assert rows(connection, sql="SELECT temp_store FROM probe") == [
            {"temp_store": _TEMP_STORE_FILE}
        ]


def test_temp_store_is_restored_after_migrations(tmp_path: Path) -> None:
    scripts = (Migration(version=1, script="CREATE TABLE t (x INTEGER);"),)
    with closing(_open(tmp_path / "restore.db", scripts=scripts)) as connection:
        assert rows(connection, sql="PRAGMA temp_store") == [{"temp_store": _TEMP_STORE_DEFAULT}]


def test_a_failing_second_script_rolls_back_the_first_and_keeps_the_starting_version(
    tmp_path: Path,
) -> None:
    path = tmp_path / "echec.db"
    bad_script = "CREATE TABLE disparait (x INTEGER);\nINSERT INTO inexistante VALUES (1);"
    with pytest.raises(MigrationError, match="^migration 2 failed: no such table: inexistante"):
        _open(
            path,
            scripts=(
                Migration(version=1, script="CREATE TABLE annulee (x INTEGER);"),
                Migration(version=2, script=bad_script),
            ),
        )
    assert _version_and_tables(path) == (0, set())


# Seconds of virtual machine instructions, unless the progress handler interrupts them.
_TEN_MILLION_STEPS = (
    "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r WHERE x < 10000000)"
    " SELECT count(*) FROM r;"
)


def test_a_shutdown_requested_during_a_migration_rolls_the_whole_block_back(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stopped.db"
    scripts = (
        Migration(version=1, script="CREATE TABLE a (x INTEGER);"),
        Migration(version=2, script="CREATE TABLE b (x INTEGER);"),
        Migration(
            version=3,
            script=f"CREATE TABLE c (x INTEGER);\nSELECT request_shutdown();\n{_TEN_MILLION_STEPS}",
        ),
    )
    _open(path, scripts=scripts[:1]).close()
    message = f"the migrations of {path} rolled back at migration 3, the database left at version 1"
    with pytest.raises(OpeningInterruptedError, match=f"^{re.escape(message)}$"):
        database_opener_with_shutdown(ShutdownFlag()).open(path, scripts=scripts)
    assert _version_and_tables(path) == (1, {"a"})


def test_a_shutdown_requested_before_the_migrations_stops_the_opening_at_its_version(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stopped.db"
    scripts = (
        Migration(version=1, script="CREATE TABLE a (x INTEGER);"),
        Migration(version=2, script="CREATE TABLE b (x INTEGER);"),
    )
    _open(path, scripts=scripts[:1]).close()
    shutdown = ShutdownFlag()
    shutdown.request()
    message = f"the opening of {path} stopped, the database at version 1"
    with pytest.raises(OpeningInterruptedError, match=f"^{re.escape(message)}$"):
        database_opener_with_shutdown(shutdown).open(path, scripts=scripts)
    assert _version_and_tables(path) == (1, {"a"})


_TWENTY_THOUSAND = "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r WHERE x < 20000)"
# Enough virtual machine instructions to meet the shutdown check, in a copy, a digest or a VACUUM.
_A_HOLDING_ROWS = f"CREATE TABLE a (x INTEGER);\n{_TWENTY_THOUSAND} INSERT INTO a SELECT x FROM r;"
_COPIED_AFTER = Migration(version=2, script="CREATE TABLE b (x INTEGER);", copy_before=True)


def test_a_shutdown_requested_during_the_pre_migration_copy_stops_it_at_its_version(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stopped.db"
    scripts = (Migration(version=1, script=_A_HOLDING_ROWS), _COPIED_AFTER)
    _open(path, scripts=scripts[:1]).close()
    opener = database_opener_with_shutdown(ShutdownFlag(), requested_by_the_copier=True)
    message = f"the pre-migration copy of {path} stopped, the database at version 1"
    with pytest.raises(OpeningInterruptedError, match=f"^{re.escape(message)}$"):
        opener.open(path, scripts=scripts)
    assert _version_and_tables(path) == (1, {"a"})
    assert [name for name in _copy_names(tmp_path) if name.endswith("_UTC")] == []


def test_a_shutdown_requested_during_the_comparison_with_an_earlier_copy_stops_it(
    *, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "stopped.db"
    scripts = (Migration(version=1, script="CREATE TABLE a (x INTEGER);"), _COPIED_AFTER)
    _open(path, scripts=scripts[:1]).close()
    earlier = tmp_path / "stopped.db.pre-0002.2026-06-11_00-00-00_UTC"
    # Its digest alone meets the check: the database's own is too short to.
    with closing(sqlite3.connect(earlier, autocommit=True)) as candidate:
        candidate.executescript(_A_HOLDING_ROWS)
    opener = database_opener_with_shutdown(ShutdownFlag(), requested_by_the_copier=True)
    message = f"the pre-migration copy of {path} stopped, the database at version 1"
    with (
        caplog.at_level("INFO"),
        pytest.raises(OpeningInterruptedError, match=f"^{re.escape(message)}$"),
    ):
        opener.open(path, scripts=scripts)
    assert caplog.messages == [
        f"pre-migration copy of {path}: comparing with {earlier}, the copy an earlier start made, "
        "to reuse it if it still matches; a stop now costs only the time spent"
    ]
    assert _copy_names(tmp_path) == [earlier.name]


def test_a_shutdown_requested_during_the_reclaim_stops_it_its_free_pages_kept(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stopped.db"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(f"{_A_HOLDING_ROWS}\nDELETE FROM a WHERE x > 5000;")
    free_pages = _page_and_free_counts(path)[1]
    opener = database_opener_with_shutdown(ShutdownFlag(), requested_by_the_opener=True)
    message = (
        f"the reclaim of {path} stopped, the database at version 0, its free pages not given back"
    )
    with pytest.raises(OpeningInterruptedError, match=f"^{re.escape(message)}$"):
        opener.open(path, scripts=())
    assert _page_and_free_counts(path)[1] == free_pages


@pytest.mark.parametrize(
    "scripts",
    [(Migration(version=1, script="CREATE TABLE a (x INTEGER);"),), ()],
    ids=["after a block", "nothing pending"],
)
def test_a_shutdown_requested_once_opened_interrupts_no_statement(
    *, tmp_path: Path, scripts: tuple[Migration, ...]
) -> None:
    shutdown = ShutdownFlag()
    opener = database_opener_with_shutdown(shutdown)
    with closing(opener.open(tmp_path / "opened.db", scripts=scripts)) as connection:
        shutdown.request()
        assert rows(connection, sql=f"{_TWENTY_THOUSAND} SELECT count(*) AS n FROM r") == [
            {"n": 20000}
        ]


def test_a_migration_over_an_instant_without_a_time_zone_names_it(tmp_path: Path) -> None:
    path = tmp_path / "naive.db"
    with pytest.raises(
        MigrationError,
        match=r"^migration 2 failed: iso_to_micros\('2026-07-04 12:00'\) raised ValueError:"
        r" instant_to_micros requires an aware datetime$",
    ):
        _open(
            path,
            scripts=(
                Migration(version=1, script="CREATE TABLE t (stamp);"),
                Migration(
                    version=2,
                    script="INSERT INTO t VALUES ('2026-07-04 12:00');\n"
                    "UPDATE t SET stamp = iso_to_micros(stamp);",
                ),
            ),
        )
    assert _version_and_tables(path) == (0, set())


def test_a_full_disk_during_the_block_rolls_it_back_and_raises_out_of_space(
    tmp_path: Path,
) -> None:
    path = tmp_path / "full.db"
    free_bytes = FakeFreeBytes(123_000_000)
    opener = database_opener_setting("PRAGMA max_page_count = 8", free_bytes=free_bytes.free_bytes)
    fill = "INSERT INTO t VALUES (zeroblob(64 * 4096));"
    with pytest.raises(OutOfSpaceError) as refusal:
        opener.open(
            path,
            scripts=(
                Migration(version=1, script="CREATE TABLE t (b BLOB);"),
                Migration(version=2, script=fill),
            ),
        )
    assert str(refusal.value) == (
        f"migrations of {path} (migration 2): out of space in {tmp_path}, 0.1 GB free; "
        "the database left at version 0"
    )
    assert free_bytes.directories == [tmp_path]
    assert _version_and_tables(path) == (0, set())


def test_a_full_disk_whose_free_space_cannot_be_measured_raises_a_migration_error(
    tmp_path: Path,
) -> None:
    """The directory moved away under the open connection: ``statvfs`` refuses its old path."""
    directory = tmp_path / "data"
    directory.mkdir()
    path = directory / "full.db"

    def fill_up_then_move_away(connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA max_page_count = 8")
        directory.rename(tmp_path / "moved")

    opener = database_opener_preparing(
        fill_up_then_move_away,
        free_bytes=lambda directory: ShutilFreeSpaceMeter(directory).free_bytes(),
    )
    with pytest.raises(MigrationError) as refusal:
        opener.open(
            path,
            scripts=(
                Migration(version=1, script="CREATE TABLE t (b BLOB);"),
                Migration(version=2, script="INSERT INTO t VALUES (zeroblob(64 * 4096));"),
            ),
        )
    assert str(refusal.value) == (
        f"migrations of {path} (migration 2): out of space in {directory}, free space of "
        f"{directory} unknown: No such file or directory; "
        "the database left at version 0"
    )


def test_the_free_space_after_a_full_disk_is_measured_once_the_wal_is_emptied(
    tmp_path: Path,
) -> None:
    """The rolled-back block's frames would count as used space the operator does not hold."""
    path = tmp_path / "full.db"
    wal_bytes_measured: list[int] = []

    def free_bytes(directory: Path) -> int:
        wal_bytes_measured.append(Path(f"{path}-wal").stat().st_size)
        return 0

    opener = database_opener_setting("PRAGMA max_page_count = 8", free_bytes=free_bytes)
    fill = "PRAGMA cache_size = 1;\nINSERT INTO t VALUES (zeroblob(64 * 4096));"
    with pytest.raises(OutOfSpaceError):
        opener.open(
            path,
            scripts=(
                Migration(version=1, script="CREATE TABLE t (b BLOB);"),
                Migration(version=2, script=fill),
            ),
        )
    assert wal_bytes_measured == [0]


def test_each_applied_script_logs_one_line_before_it_runs(
    *, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A long first boot shows which script runs, so a silent wait is not taken for a hang."""
    path = tmp_path / "log.db"
    scripts = (
        Migration(version=1, script="CREATE TABLE a (x INTEGER);"),
        Migration(version=2, script="CREATE TABLE b (x INTEGER);"),
    )
    _open(path, scripts=scripts[:1]).close()
    caplog.clear()
    with caplog.at_level("INFO"):
        _open(path, scripts=scripts).close()
    assert [message for message in caplog.messages if message.endswith(": applying")] == [
        "migration 2: applying"
    ]


def test_the_block_is_announced_then_the_migration_running_every_30_s(
    *, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "ticked.db"
    scripts = (
        Migration(version=1, script="CREATE TABLE a (x INTEGER);"),
        Migration(version=2, script="CREATE TABLE b (x INTEGER);\nSELECT tick();"),
        Migration(version=3, script="CREATE TABLE c (x INTEGER);\nSELECT tick();"),
    )
    _open(path, scripts=scripts[:1]).close()
    ticker = FakeTicker()
    caplog.clear()
    with caplog.at_level("INFO"):
        database_opener_ticked_by(ticker).open(path, scripts=scripts).close()
    assert caplog.messages == [
        f"migrations of {path}: from version 1 to version 3 in one step; "
        "a stop now rolls them back, costing only the time spent",
        "migration 2: applying",
        f"migrations of {path}: migration 2 running, 30 s since the block began",
        "migration 3: applying",
        f"migrations of {path}: migration 3 running, 60 s since the block began",
    ]
    assert ticker.periods == [timedelta(seconds=30)]


def test_stray_commit_in_a_script_is_detected_before_the_version_is_written(
    tmp_path: Path,
) -> None:
    # A COMMIT inside a script commits the block so far without its schema version: the version
    # stays the starting one, and the earlier scripts' work cannot be taken back.
    path = tmp_path / "commit.db"
    with pytest.raises(
        MigrationError, match=r"^migration 2: the script closed the migrations' transaction"
    ):
        _open(
            path,
            scripts=(
                Migration(version=1, script="CREATE TABLE survit (x INTEGER);"),
                Migration(version=2, script="COMMIT;"),
            ),
        )
    assert _version_and_tables(path) == (0, {"survit"})


def test_stray_commit_followed_by_a_failure_keeps_the_starting_version(tmp_path: Path) -> None:
    # Attack variant 2: a stray COMMIT THEN a statement that fails. The work
    # committed by the stray COMMIT is unrecoverable, but the version MUST NOT
    # be written (otherwise the migration would be marked applied even though it failed).
    path = tmp_path / "commit2.db"
    script = "CREATE TABLE t (x INTEGER);\nCOMMIT;\nINSERT INTO inexistante VALUES (1);"
    with pytest.raises(MigrationError, match="migration 1"):
        _open(path, scripts=(Migration(version=1, script=script),))
    assert _version_and_tables(path)[0] == 0


def test_open_closes_the_connection_when_configuring_fails(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    path.write_bytes(b"not a database" * 100)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(PersistenceError, match="not a database"):
            _open(path, scripts=())
        # A connection left open warns when it is collected.
        gc.collect()
    assert [w for w in caught if issubclass(w.category, ResourceWarning)] == []


def test_a_vacuum_in_a_script_fails_inside_the_block(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "0001_vacuum.sql").write_text("VACUUM;", encoding="utf-8")
    path = tmp_path / "vacuum.db"
    with pytest.raises(MigrationError, match="cannot VACUUM from within a transaction"):
        _open(path, scripts=load_scripts(scripts))
    assert _version_and_tables(path)[0] == 0


def test_the_pragmas_a_script_sets_end_with_the_block(tmp_path: Path) -> None:
    script = "PRAGMA secure_delete = FAST;\nPRAGMA cache_size = -262144;\nCREATE TABLE t (x);"
    scripts = (Migration(version=1, script=script),)
    with closing(sqlite3.connect(":memory:")) as fresh:
        build_pragmas = rows(fresh, sql="SELECT * FROM pragma_secure_delete, pragma_cache_size")
    with closing(_open(tmp_path / "pragmas.db", scripts=scripts)) as connection:
        pragmas = rows(connection, sql="SELECT * FROM pragma_secure_delete, pragma_cache_size")
    assert pragmas == build_pragmas


# --- The reclaim: at a quarter of free pages, after a block of migrations as at any opening ---


def _page_and_free_counts(path: Path) -> tuple[int, int]:
    with closing(sqlite3.connect(path)) as connection:
        (row,) = rows(
            connection,
            sql="SELECT page_count, freelist_count"
            " FROM pragma_page_count(), pragma_freelist_count()",
        )
        return row["page_count"], row["freelist_count"]


def _with_free_pages(path: Path, *, kept_pages: int, freed_pages: int) -> tuple[int, int]:
    """A database at version 0 in WAL, its ``kept`` table, then ``freed_pages`` free once its
    ``freed`` table dropped; its page and free counts."""
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        # Each 4092 bytes of a blob past the first fills one overflow page.
        connection.execute("CREATE TABLE kept (b BLOB)")
        connection.execute("INSERT INTO kept VALUES (zeroblob(?))", (kept_pages * 4092,))
        connection.execute("CREATE TABLE freed (b BLOB)")
        connection.execute("INSERT INTO freed VALUES (zeroblob(?))", ((freed_pages - 1) * 4092,))
        connection.execute("DROP TABLE freed")
    return _page_and_free_counts(path)


def _block_freeing(pages: int) -> tuple[Migration, ...]:
    """A block of migrations that keeps a table and frees ``pages`` pages."""
    return (
        Migration(version=1, script="CREATE TABLE kept (b BLOB);"),
        Migration(version=2, script="INSERT INTO kept VALUES (zeroblob(14 * 4092));"),
        Migration(
            version=3,
            script="CREATE TABLE freed (b BLOB);\n"
            f"INSERT INTO freed VALUES (zeroblob({pages - 1} * 4092));\nDROP TABLE freed;",
        ),
    )


def test_a_block_of_migrations_leaving_a_quarter_free_is_compacted_after_it(
    tmp_path: Path,
) -> None:
    path = tmp_path / "block.db"
    _open(path, scripts=_block_freeing(6)).close()
    assert _page_and_free_counts(path)[1] == 0


def test_a_block_of_migrations_leaving_less_than_a_quarter_free_is_not_compacted(
    tmp_path: Path,
) -> None:
    """A block that frees nothing, a column added, rewrites no catalog."""
    path = tmp_path / "block.db"
    _open(path, scripts=_block_freeing(5)).close()
    assert _page_and_free_counts(path) == (21, 5)


def test_a_shutdown_requested_as_the_block_commits_stops_the_opening_before_the_reclaim(
    tmp_path: Path,
) -> None:
    path = tmp_path / "block.db"
    # The block's last statement: none after it runs long enough to meet the check.
    scripts = (*_block_freeing(6), Migration(version=4, script="SELECT request_shutdown();"))
    message = f"the opening of {path} stopped, the database at version 4"
    with pytest.raises(OpeningInterruptedError, match=f"^{re.escape(message)}$"):
        database_opener_with_shutdown(ShutdownFlag()).open(path, scripts=scripts)
    assert _version_and_tables(path)[0] == 4
    assert _page_and_free_counts(path)[1] == 6


def test_the_reclaim_leaves_the_wal_empty(tmp_path: Path) -> None:
    """The crawler holds its connection for good, so a WAL the reclaim grew would never shrink."""
    path = tmp_path / "wal.db"
    _with_free_pages(path, kept_pages=10, freed_pages=4)
    with closing(_open(path, scripts=())):
        assert Path(f"{path}-wal").stat().st_size == 0


def test_an_opening_with_nothing_pending_compacts_a_quarter_free(tmp_path: Path) -> None:
    path = tmp_path / "quarter.db"
    assert _with_free_pages(path, kept_pages=10, freed_pages=4) == (16, 4)
    _open(path, scripts=()).close()
    assert _page_and_free_counts(path)[1] == 0


def test_the_reclaim_is_announced_with_the_space_it_gives_back(
    *, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "announced.db"
    assert _with_free_pages(path, kept_pages=10, freed_pages=4) == (16, 4)
    with caplog.at_level("INFO"):
        _open(path, scripts=()).close()
    assert caplog.messages == [
        f"reclaim of {path}: giving back {gigabytes(4 * 4096)} of free pages, 25 % of the file; "
        "a stop now costs only the time spent"
    ]


def test_the_reclaim_reports_every_30_s_while_it_runs(
    *, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "ticked.db"
    _with_free_pages(path, kept_pages=10, freed_pages=4)
    ticker = FakeTicker()
    with caplog.at_level("INFO"):
        database_opener_ticked_by_progress(ticker).open(path, scripts=()).close()
    assert caplog.messages[1:3] == [
        f"reclaim of {path}: giving back free pages, 30 s elapsed",
        f"reclaim of {path}: giving back free pages, 60 s elapsed",
    ]
    assert ticker.periods == [timedelta(seconds=30)]


def test_an_opening_with_nothing_pending_leaves_less_than_a_quarter_free(tmp_path: Path) -> None:
    path = tmp_path / "below.db"
    assert _with_free_pages(path, kept_pages=11, freed_pages=4) == (17, 4)
    _open(path, scripts=()).close()
    assert _page_and_free_counts(path) == (17, 4)


def test_a_failed_reclaim_raises_a_migration_error(tmp_path: Path) -> None:
    path = tmp_path / "held.db"
    _with_free_pages(path, kept_pages=4, freed_pages=4)
    opener = database_opener_setting("PRAGMA busy_timeout = 0")
    with closing(sqlite3.connect(path, autocommit=True)) as holder:
        holder.execute("BEGIN IMMEDIATE")
        with pytest.raises(MigrationError, match="^reclaim failed: database is locked"):
            opener.open(path, scripts=())


# --- After a block: the connection opened again, the memory given back ---

_ONE_SCRIPT = (Migration(version=1, script="CREATE TABLE t (x);"),)


def test_an_opening_that_migrated_returns_a_connection_opened_after_the_block(
    tmp_path: Path,
) -> None:
    opener = database_opener_registering("migrated_here")
    with (
        closing(opener.open(tmp_path / "catalog.db", scripts=_ONE_SCRIPT)) as connection,
        pytest.raises(sqlite3.OperationalError, match="no such function: migrated_here"),
    ):
        connection.execute("SELECT migrated_here()")


def test_an_opening_with_nothing_pending_returns_its_first_connection(tmp_path: Path) -> None:
    opener = database_opener_registering("opened_here")
    with closing(opener.open(tmp_path / "catalog.db", scripts=())) as connection:
        assert rows(connection, sql="SELECT opened_here() AS here") == [{"here": 0}]


def test_an_opening_that_migrated_leaves_no_connection_open(tmp_path: Path) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _open(tmp_path / "catalog.db", scripts=_ONE_SCRIPT).close()
        # A connection left open warns when it is collected.
        gc.collect()
    assert [w for w in caught if issubclass(w.category, ResourceWarning)] == []


@pytest.mark.parametrize(
    ("scripts", "release_count"),
    [(_ONE_SCRIPT, 1), ((), 0)],
    ids=["after a block", "nothing pending"],
)
def test_an_opening_releases_the_memory_once_after_a_block(
    *, tmp_path: Path, scripts: tuple[Migration, ...], release_count: int
) -> None:
    memory_releaser = FakeMemoryReleaser()
    opener = database_opener(memory_releaser=memory_releaser)
    opener.open(tmp_path / "catalog.db", scripts=scripts).close()
    assert memory_releaser.release_count == release_count
