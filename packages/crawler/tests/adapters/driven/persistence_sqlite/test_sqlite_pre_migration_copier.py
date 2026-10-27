import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.connection import (
    Migration,
    apply_migrations,
    connect,
    load_scripts,
    pending_migrations,
)
from p2pwatch.adapters.driven.persistence_sqlite.errors import MigrationError
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_pre_migration_copier import (
    SqlitePreMigrationCopier,
)
from tests.fakes.adapters.driven.fake_free_bytes import FakeFreeBytes
from tests.fakes.adapters.driven.fake_time import FakeTime

_AMPLE_BYTES = 1 << 62
_SEED = ("CREATE TABLE t (x INTEGER);", "INSERT INTO t VALUES (1), (2);")
_COPY_BEFORE = "-- migration: copy-before\n"
# FakeTime's start, 2026-06-12 00:00:00 UTC.
_COPY_NAME = "catalog.db.pre-0003.2026-06-12_00-00-00_UTC"


def _scripts(directory: Path, *pending: str) -> tuple[Migration, ...]:
    directory.mkdir()
    for version, script in enumerate((*_SEED, *pending), start=1):
        (directory / f"{version:04d}_script.sql").write_text(script, encoding="utf-8")
    return load_scripts(directory)


def _seeded(path: Path, scripts: tuple[Migration, ...]) -> sqlite3.Connection:
    """A database at version 2, its two rows in ``t``, the later scripts pending."""
    path.parent.mkdir()
    connection = connect(path)
    apply_migrations(connection, pending_migrations(connection, scripts[: len(_SEED)]))
    return connection


def _copier(free_bytes: FakeFreeBytes | None = None) -> SqlitePreMigrationCopier:
    free_bytes = free_bytes or FakeFreeBytes(_AMPLE_BYTES)
    return SqlitePreMigrationCopier(FakeTime().wall, free_bytes.free_bytes)


def _copy_names(directory: Path) -> list[str]:
    return sorted(file.name for file in directory.iterdir() if ".pre-" in file.name)


def test_no_marked_pending_migration_makes_no_copy(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", "CREATE TABLE u (y);", "CREATE TABLE v (z);")
    path = tmp_path / "data" / "catalog.db"
    with closing(_seeded(path, scripts)) as connection:
        _copier().ensure_copy(connection, path, pending_migrations(connection, scripts))
    assert _copy_names(path.parent) == []


def test_a_marked_migration_second_among_the_pending_copies_before_the_first(
    tmp_path: Path,
) -> None:
    scripts = _scripts(tmp_path / "scripts", "CREATE TABLE u (y);", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    with closing(_seeded(path, scripts)) as connection:
        _copier().ensure_copy(connection, path, pending_migrations(connection, scripts))
    assert _copy_names(path.parent) == [_COPY_NAME]
    with closing(sqlite3.connect(f"file:{path.parent / _COPY_NAME}?mode=ro", uri=True)) as copy:
        assert copy.execute("PRAGMA user_version").fetchone()[0] == 2
        assert copy.execute("SELECT x FROM t ORDER BY x").fetchall() == [(1,), (2,)]


def test_a_new_database_is_not_copied(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    path.parent.mkdir()
    with closing(connect(path)) as connection:
        _copier().ensure_copy(connection, path, pending_migrations(connection, scripts))
    assert _copy_names(path.parent) == []


def _keep_a_wal_with_free_pages(path: Path) -> sqlite3.Connection:
    """A second connection whose writes stay in the ``-wal``, having freed pages."""
    writer = sqlite3.connect(path, autocommit=True)
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute(
        "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 2000) "
        "INSERT INTO t SELECT randomblob(500) FROM n"
    )
    writer.execute("DELETE FROM t WHERE rowid > 1000")
    return writer


def _need_bytes(connection: sqlite3.Connection, path: Path) -> int:
    """The copy's live pages and ``-wal``, then the migrations' file and ``-wal``."""
    page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
    page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
    freelist_count = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
    assert freelist_count > 0
    wal_bytes = Path(f"{path}-wal").stat().st_size
    assert wal_bytes > 0
    return (page_count - freelist_count) * page_size + wal_bytes + path.stat().st_size + wal_bytes


def test_one_byte_short_refuses_before_any_write(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    with (
        closing(_seeded(path, scripts)) as connection,
        closing(_keep_a_wal_with_free_pages(path)),
    ):
        need_bytes = _need_bytes(connection, path)
        free_bytes = FakeFreeBytes(need_bytes - 1)
        with pytest.raises(MigrationError, match=rf"\b{need_bytes}\b.*\b{need_bytes - 1}\b"):
            _copier(free_bytes).ensure_copy(
                connection, path, pending_migrations(connection, scripts)
            )
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
    assert _copy_names(path.parent) == []
    assert free_bytes.directories == [path.parent]


def test_exactly_the_free_space_needed_copies(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    with (
        closing(_seeded(path, scripts)) as connection,
        closing(_keep_a_wal_with_free_pages(path)),
    ):
        free_bytes = FakeFreeBytes(_need_bytes(connection, path))
        _copier(free_bytes).ensure_copy(connection, path, pending_migrations(connection, scripts))
    assert _copy_names(path.parent) == [_COPY_NAME]


def test_a_leftover_is_deleted_before_the_copy(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    other_database_leftover = path.parent / "local.db.pre-0003.partial"
    with closing(_seeded(path, scripts)) as connection:
        connection.execute("VACUUM INTO ?", (str(path.parent / "catalog.db.pre-0003.partial"),))
        (path.parent / "catalog.db.pre-0002.partial-journal").write_bytes(b"\0" * 512)
        other_database_leftover.write_bytes(b"local")
        _copier().ensure_copy(connection, path, pending_migrations(connection, scripts))
    assert _copy_names(path.parent) == [_COPY_NAME, other_database_leftover.name]
    with closing(sqlite3.connect(f"file:{path.parent / _COPY_NAME}?mode=ro", uri=True)) as copy:
        assert copy.execute("PRAGMA integrity_check").fetchall() == [("ok",)]


def test_a_taken_name_refuses_and_leaves_its_file(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    with closing(_seeded(path, scripts)) as connection:
        taken = path.parent / _COPY_NAME
        taken.write_bytes(b"taken")
        with pytest.raises(MigrationError, match=_COPY_NAME):
            _copier().ensure_copy(connection, path, pending_migrations(connection, scripts))
    assert taken.read_bytes() == b"taken"
    assert _copy_names(path.parent) == [_COPY_NAME]
