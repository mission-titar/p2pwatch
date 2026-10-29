import os
import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.errors import MigrationError
from p2pwatch.adapters.driven.persistence_sqlite.migration_scripts import (
    Migration,
    PendingMigrations,
    load_scripts,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    SqliteDatabaseOpener,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_pre_migration_copier import (
    SqlitePreMigrationCopier,
)
from tests.fakes.adapters.driven.fake_free_bytes import FakeFreeBytes
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    database_opener,
)

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
    return database_opener().open(path, scripts[: len(_SEED)])


def _pending(scripts: tuple[Migration, ...]) -> PendingMigrations:
    """The scripts a database ``_seeded`` from them has pending."""
    return PendingMigrations(len(_SEED), scripts[len(_SEED) :])


def _copier(
    free_bytes: FakeFreeBytes | None = None, time: FakeTime | None = None
) -> SqlitePreMigrationCopier:
    free_bytes = free_bytes or FakeFreeBytes(_AMPLE_BYTES)
    return SqlitePreMigrationCopier((time or FakeTime()).wall, free_bytes.free_bytes)


def _copy_names(directory: Path) -> list[str]:
    return sorted(file.name for file in directory.iterdir() if ".pre-" in file.name)


def test_no_marked_pending_migration_makes_no_copy(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", "CREATE TABLE u (y);", "CREATE TABLE v (z);")
    path = tmp_path / "data" / "catalog.db"
    with closing(_seeded(path, scripts)) as connection:
        _copier().ensure_copy(connection, path, _pending(scripts))
    assert _copy_names(path.parent) == []


def test_a_marked_migration_second_among_the_pending_copies_before_the_first(
    tmp_path: Path,
) -> None:
    scripts = _scripts(tmp_path / "scripts", "CREATE TABLE u (y);", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    with closing(_seeded(path, scripts)) as connection:
        _copier().ensure_copy(connection, path, _pending(scripts))
    assert _copy_names(path.parent) == [_COPY_NAME]
    with closing(sqlite3.connect(f"file:{path.parent / _COPY_NAME}?mode=ro", uri=True)) as copy:
        assert rows(copy, "PRAGMA user_version") == [{"user_version": 2}]
        assert rows(copy, "SELECT x FROM t ORDER BY x") == [{"x": 1}, {"x": 2}]


def test_a_new_database_is_not_copied(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    path.parent.mkdir()
    with closing(database_opener().open(path, ())) as connection:
        _copier().ensure_copy(connection, path, PendingMigrations(0, scripts))
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
    page_size = _pragma(connection, "page_size")
    page_count = _pragma(connection, "page_count")
    freelist_count = _pragma(connection, "freelist_count")
    assert freelist_count > 0
    wal_bytes = Path(f"{path}-wal").stat().st_size
    assert wal_bytes > 0
    return (page_count - freelist_count) * page_size + wal_bytes + path.stat().st_size + wal_bytes


def _pragma(connection: sqlite3.Connection, name: str) -> int:
    [pragma] = rows(connection, f"PRAGMA {name}")
    return int(pragma[name])


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
            _copier(free_bytes).ensure_copy(connection, path, _pending(scripts))
        assert rows(connection, "PRAGMA user_version") == [{"user_version": 2}]
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
        _copier(free_bytes).ensure_copy(connection, path, _pending(scripts))
    assert _copy_names(path.parent) == [_COPY_NAME]


def test_a_leftover_is_deleted_before_the_copy(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    other_database_leftover = path.parent / "local.db.pre-0003.partial"
    with closing(_seeded(path, scripts)) as connection:
        connection.execute("VACUUM INTO ?", (str(path.parent / "catalog.db.pre-0003.partial"),))
        (path.parent / "catalog.db.pre-0002.partial-journal").write_bytes(b"\0" * 512)
        other_database_leftover.write_bytes(b"local")
        _copier().ensure_copy(connection, path, _pending(scripts))
    assert _copy_names(path.parent) == [_COPY_NAME, other_database_leftover.name]
    with closing(sqlite3.connect(f"file:{path.parent / _COPY_NAME}?mode=ro", uri=True)) as copy:
        assert rows(copy, "PRAGMA integrity_check") == [{"integrity_check": "ok"}]


def test_a_taken_name_refuses_and_leaves_its_file(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    with closing(_seeded(path, scripts)) as connection:
        taken = path.parent / _COPY_NAME
        taken.write_bytes(b"taken")
        with pytest.raises(MigrationError, match=_COPY_NAME):
            _copier().ensure_copy(connection, path, _pending(scripts))
    assert taken.read_bytes() == b"taken"
    assert _copy_names(path.parent) == [_COPY_NAME]


def test_a_link_the_filesystem_refuses_raises_a_migration_error(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    # The longest name whose .partial-journal fits NAME_MAX, 255: its final name does not.
    path = tmp_path / "data" / ("c" * (255 - len(".pre-0003.partial-journal")))
    final_name = f"{path.name}.pre-0003.2026-06-12_00-00-00_UTC"
    with (
        closing(_seeded(path, scripts)) as connection,
        pytest.raises(MigrationError, match=rf"{final_name}\b.*File name too long"),
    ):
        _copier().ensure_copy(connection, path, _pending(scripts))
    assert _copy_names(path.parent) == []


def test_a_copy_of_a_database_named_by_a_relative_path_is_reused(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    # A URI escapes these characters.
    path = tmp_path / "data #%?" / "catalog.db"
    _seeded(path, scripts).close()
    relative_path = Path(os.path.relpath(path))
    time = FakeTime()
    copier = _copier(time=time)
    with closing(database_opener().open(relative_path, scripts[: len(_SEED)])) as connection:
        copier.ensure_copy(connection, relative_path, _pending(scripts))
        time.advance(timedelta(minutes=1))
        copier.ensure_copy(connection, relative_path, _pending(scripts))
    assert _copy_names(path.parent) == [_COPY_NAME]


_FAILING = _COPY_BEFORE + "DELETE FROM t;\nINSERT INTO absent VALUES (1);"


def _open(path: Path, scripts: tuple[Migration, ...], copier: SqlitePreMigrationCopier) -> None:
    """An open over the scripts through ``copier``, then the connection closed."""
    SqliteDatabaseOpener(copier).open(path, scripts).close()


def test_a_failed_migration_is_retried_on_the_same_copy(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _FAILING)
    path = tmp_path / "data" / "catalog.db"
    _seeded(path, scripts).close()
    time = FakeTime()
    copier = _copier(time=time)
    with pytest.raises(MigrationError, match="migration 3"):
        _open(path, scripts, copier)
    first = (path.parent / _COPY_NAME).stat()
    time.advance(timedelta(minutes=1))
    (path.parent / "catalog.db.pre-0003.partial").write_bytes(b"a copy a stop interrupted")
    with pytest.raises(MigrationError, match="migration 3"):
        _open(path, scripts, copier)
    assert _copy_names(path.parent) == [_COPY_NAME]
    again = (path.parent / _COPY_NAME).stat()
    assert (again.st_ino, again.st_mtime_ns) == (first.st_ino, first.st_mtime_ns)


def test_a_changed_database_gets_a_new_copy(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _FAILING)
    path = tmp_path / "data" / "catalog.db"
    _seeded(path, scripts).close()
    time = FakeTime()
    copier = _copier(time=time)
    with pytest.raises(MigrationError, match="migration 3"):
        _open(path, scripts, copier)
    first_bytes = (path.parent / _COPY_NAME).read_bytes()
    with closing(sqlite3.connect(path, autocommit=True)) as writer:
        writer.execute("INSERT INTO t VALUES (3)")
    time.advance(timedelta(minutes=1))
    with pytest.raises(MigrationError, match="migration 3"):
        _open(path, scripts, copier)
    second_name = "catalog.db.pre-0003.2026-06-12_00-01-00_UTC"
    assert _copy_names(path.parent) == [_COPY_NAME, second_name]
    assert (path.parent / _COPY_NAME).read_bytes() == first_bytes


def test_an_unreadable_candidate_is_not_reused(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    time = FakeTime()
    copier = _copier(time=time)
    junk = path.parent / "catalog.db.pre-0003.2026-06-12_00-01-00_UTC"
    with closing(_seeded(path, scripts)) as connection:
        copier.ensure_copy(connection, path, _pending(scripts))
        junk.write_bytes(b"junk" * 1024)
        time.advance(timedelta(minutes=2))
        copier.ensure_copy(connection, path, _pending(scripts))
    second_name = "catalog.db.pre-0003.2026-06-12_00-02-00_UTC"
    assert _copy_names(path.parent) == [_COPY_NAME, junk.name, second_name]
    assert junk.read_bytes() == b"junk" * 1024
