import errno
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
    Linker,
    SqlitePreMigrationCopier,
    _rename_without_replacing,
)
from p2pwatch.domain.out_of_space_error import OutOfSpaceError
from tests.fakes.adapters.driven.fake_free_bytes import FakeFreeBytes
from tests.fakes.adapters.driven.fake_memory_releaser import FakeMemoryReleaser
from tests.fakes.adapters.driven.fake_ticker import FakeTicker
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    database_opener,
    open_reader,
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


def _seeded(path: Path, *, scripts: tuple[Migration, ...]) -> sqlite3.Connection:
    """A database at version 2, its two rows in ``t``, the later scripts pending."""
    path.parent.mkdir()
    return database_opener().open(path, scripts=scripts[: len(_SEED)])


def _pending(scripts: tuple[Migration, ...]) -> PendingMigrations:
    """The scripts a database ``_seeded`` from them has pending."""
    return PendingMigrations(current_version=len(_SEED), migrations=scripts[len(_SEED) :])


def _copier(
    free_bytes: FakeFreeBytes | None = None,
    *,
    time: FakeTime | None = None,
    ticker: FakeTicker | None = None,
) -> SqlitePreMigrationCopier:
    free_bytes = free_bytes or FakeFreeBytes(_AMPLE_BYTES)
    return SqlitePreMigrationCopier(
        (time or FakeTime()).wall, ticker=ticker or FakeTicker(), free_bytes=free_bytes.free_bytes
    )


def _copy_names(directory: Path) -> list[str]:
    return sorted(file.name for file in directory.iterdir() if ".pre-" in file.name)


def test_no_marked_pending_migration_makes_no_copy(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", "CREATE TABLE u (y);", "CREATE TABLE v (z);")
    path = tmp_path / "data" / "catalog.db"
    with closing(_seeded(path, scripts=scripts)) as connection:
        _copier().ensure_copy(
            connection, path=path, pending=_pending(scripts), open_reader=open_reader
        )
    assert _copy_names(path.parent) == []


def test_a_marked_migration_second_among_the_pending_copies_before_the_first(
    tmp_path: Path,
) -> None:
    scripts = _scripts(tmp_path / "scripts", "CREATE TABLE u (y);", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    with closing(_seeded(path, scripts=scripts)) as connection:
        _copier().ensure_copy(
            connection, path=path, pending=_pending(scripts), open_reader=open_reader
        )
    assert _copy_names(path.parent) == [_COPY_NAME]
    with closing(sqlite3.connect(f"file:{path.parent / _COPY_NAME}?mode=ro", uri=True)) as copy:
        assert rows(copy, sql="PRAGMA user_version") == [{"user_version": 2}]
        assert rows(copy, sql="SELECT x FROM t ORDER BY x") == [{"x": 1}, {"x": 2}]


def _gb(size_bytes: int) -> str:
    return f"{size_bytes / 1e9:.1f} GB"


def test_the_copy_is_announced_then_its_share_written_every_30_s(
    *, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    partial = path.parent / "catalog.db.pre-0003.partial"
    ticker = FakeTicker()
    written: list[int] = []

    def tick_once_partly_written() -> int:
        if not written and partial.exists() and partial.stat().st_size > 0:
            written.append(partial.stat().st_size)
            ticker.tick()
        return 0

    with closing(_seeded(path, scripts=scripts)) as connection:
        connection.execute(
            "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 400) "
            "INSERT INTO t SELECT randomblob(500) FROM n"
        )
        connection.execute("DELETE FROM t WHERE rowid > 300")
        live_bytes = _pragma(connection, name="page_size") * (
            _pragma(connection, name="page_count") - _pragma(connection, name="freelist_count")
        )
        # A cache of one page spills the copy to its file while it is written.
        connection.execute("PRAGMA cache_size=1")
        connection.set_progress_handler(tick_once_partly_written, 100)
        with caplog.at_level("INFO"):
            _copier(ticker=ticker).ensure_copy(
                connection, path=path, pending=_pending(scripts), open_reader=open_reader
            )
    [written_bytes] = written
    assert 0 < written_bytes < live_bytes
    assert caplog.messages == [
        f"pre-migration copy of {path}: writing {_gb(live_bytes)} to {partial}; "
        "a stop now costs only the time spent",
        f"pre-migration copy of {path}: {_gb(written_bytes)} of {_gb(live_bytes)} written "
        f"({written_bytes * 100 // live_bytes} %)",
        f"pre-migration copy: {path.parent / _COPY_NAME}",
    ]
    assert ticker.periods == [timedelta(seconds=30)]


def test_a_tick_before_the_copy_s_file_exists_reports_nothing_written(
    *, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    partial = path.parent / "catalog.db.pre-0003.partial"
    ticker = FakeTicker()
    ticked: list[bool] = []

    def tick_once_before_the_file() -> int:
        # Once the copy's run has begun: the free-space check reads the database before it.
        if not ticked and ticker.periods and not partial.exists():
            ticked.append(True)
            ticker.tick()
        return 0

    with closing(_seeded(path, scripts=scripts)) as connection:
        live_bytes = _pragma(connection, name="page_size") * _pragma(connection, name="page_count")
        connection.set_progress_handler(tick_once_before_the_file, 1)
        with caplog.at_level("INFO"):
            _copier(ticker=ticker).ensure_copy(
                connection, path=path, pending=_pending(scripts), open_reader=open_reader
            )
    assert ticked
    assert caplog.messages[1] == (
        f"pre-migration copy of {path}: {_gb(0)} of {_gb(live_bytes)} written (0 %)"
    )


def test_the_comparison_with_an_earlier_copy_is_announced_then_its_time_every_30_s(
    *, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    copy = path.parent / _COPY_NAME
    ticker = FakeTicker()
    copier = _copier(ticker=ticker)
    ticked: list[bool] = []

    def tick_once() -> int:
        if not ticked:
            ticked.append(True)
            ticker.tick()
        return 0

    with closing(_seeded(path, scripts=scripts)) as connection:
        copier.ensure_copy(
            connection, path=path, pending=_pending(scripts), open_reader=open_reader
        )
        caplog.clear()
        ticker.periods.clear()
        connection.set_progress_handler(tick_once, 1)
        with caplog.at_level("INFO"):
            copier.ensure_copy(
                connection, path=path, pending=_pending(scripts), open_reader=open_reader
            )
    assert caplog.messages == [
        f"pre-migration copy of {path}: comparing with {copy}, the copy an earlier start made, "
        "to reuse it if it still matches; a stop now costs only the time spent",
        f"pre-migration copy of {path}: comparing, 30 s elapsed",
        f"pre-migration copy of {path}: reusing {copy}",
    ]
    assert ticker.periods == [timedelta(seconds=30)]


def test_an_interrupted_copy_is_named_as_it_is_deleted(
    *, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    scripts = _scripts(tmp_path / "scripts", "CREATE TABLE u (y);")
    path = tmp_path / "data" / "catalog.db"
    partial = path.parent / "catalog.db.pre-0003.partial"
    with closing(_seeded(path, scripts=scripts)) as connection:
        partial.write_bytes(b"a copy a stop interrupted")
        (path.parent / "catalog.db.pre-0003.partial-journal").write_bytes(b"its journal")
        with caplog.at_level("INFO"):
            _copier().ensure_copy(
                connection, path=path, pending=_pending(scripts), open_reader=open_reader
            )
    assert caplog.messages == [
        f"pre-migration copy of {path}: the previous start's copy was interrupted, "
        f"deleting {partial}; the copy starts over"
    ]
    assert _copy_names(path.parent) == []


def test_a_new_database_is_not_copied(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    path.parent.mkdir()
    with closing(database_opener().open(path, scripts=())) as connection:
        _copier().ensure_copy(
            connection,
            path=path,
            pending=PendingMigrations(current_version=0, migrations=scripts),
            open_reader=open_reader,
        )
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


def _need_bytes(connection: sqlite3.Connection, *, path: Path) -> int:
    """The copy's live pages and ``-wal``, then the migrations' file and ``-wal``."""
    page_size = _pragma(connection, name="page_size")
    page_count = _pragma(connection, name="page_count")
    freelist_count = _pragma(connection, name="freelist_count")
    assert freelist_count > 0
    wal_bytes = Path(f"{path}-wal").stat().st_size
    assert wal_bytes > 0
    return (page_count - freelist_count) * page_size + wal_bytes + path.stat().st_size + wal_bytes


def _pragma(connection: sqlite3.Connection, *, name: str) -> int:
    [pragma] = rows(connection, sql=f"PRAGMA {name}")
    return int(pragma[name])


def test_one_byte_short_refuses_before_any_write(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    with (
        closing(_seeded(path, scripts=scripts)) as connection,
        closing(_keep_a_wal_with_free_pages(path)),
    ):
        need_bytes = _need_bytes(connection, path=path)
        free_bytes = FakeFreeBytes(need_bytes - 1)
        with pytest.raises(OutOfSpaceError) as refusal:
            _copier(free_bytes).ensure_copy(
                connection, path=path, pending=_pending(scripts), open_reader=open_reader
            )
        assert str(refusal.value) == str(
            OutOfSpaceError(
                step=f"pre-migration copy of {path}",
                directory=path.parent,
                free_bytes=need_bytes - 1,
                need_bytes=need_bytes,
                outcome="nothing written",
            )
        )
        assert rows(connection, sql="PRAGMA user_version") == [{"user_version": 2}]
    assert _copy_names(path.parent) == []
    assert free_bytes.directories == [path.parent]


def test_exactly_the_free_space_needed_copies(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    with (
        closing(_seeded(path, scripts=scripts)) as connection,
        closing(_keep_a_wal_with_free_pages(path)),
    ):
        free_bytes = FakeFreeBytes(_need_bytes(connection, path=path))
        _copier(free_bytes).ensure_copy(
            connection, path=path, pending=_pending(scripts), open_reader=open_reader
        )
    assert _copy_names(path.parent) == [_COPY_NAME]


def test_a_leftover_is_deleted_before_the_copy(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    other_database_leftover = path.parent / "local.db.pre-0003.partial"
    with closing(_seeded(path, scripts=scripts)) as connection:
        connection.execute("VACUUM INTO ?", (str(path.parent / "catalog.db.pre-0003.partial"),))
        (path.parent / "catalog.db.pre-0002.partial-journal").write_bytes(b"\0" * 512)
        other_database_leftover.write_bytes(b"local")
        _copier().ensure_copy(
            connection, path=path, pending=_pending(scripts), open_reader=open_reader
        )
    assert _copy_names(path.parent) == [_COPY_NAME, other_database_leftover.name]
    with closing(sqlite3.connect(f"file:{path.parent / _COPY_NAME}?mode=ro", uri=True)) as copy:
        assert rows(copy, sql="PRAGMA integrity_check") == [{"integrity_check": "ok"}]


def test_a_taken_name_refuses_and_leaves_its_file(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    with closing(_seeded(path, scripts=scripts)) as connection:
        taken = path.parent / _COPY_NAME
        taken.write_bytes(b"taken")
        with pytest.raises(MigrationError, match=_COPY_NAME):
            _copier().ensure_copy(
                connection, path=path, pending=_pending(scripts), open_reader=open_reader
            )
    assert taken.read_bytes() == b"taken"
    assert _copy_names(path.parent) == [_COPY_NAME]


def test_a_link_the_filesystem_refuses_raises_a_migration_error(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    # The longest name whose .partial-journal fits NAME_MAX, 255: its final name does not.
    path = tmp_path / "data" / ("c" * (255 - len(".pre-0003.partial-journal")))
    final_name = f"{path.name}.pre-0003.2026-06-12_00-00-00_UTC"
    with (
        closing(_seeded(path, scripts=scripts)) as connection,
        pytest.raises(MigrationError, match=rf"{final_name}\b.*File name too long"),
    ):
        _copier().ensure_copy(
            connection, path=path, pending=_pending(scripts), open_reader=open_reader
        )
    assert _copy_names(path.parent) == []


def _link_refused_with(code: int) -> Linker:
    def refused_link(source: Path, destination: Path) -> None:  # noqa: PLR0917
        raise OSError(code, os.strerror(code), str(source), None, str(destination))

    return refused_link


@pytest.mark.parametrize("code", [errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP])
def test_a_copy_where_hard_links_are_refused_is_published_by_a_rename(
    *, tmp_path: Path, code: int
) -> None:
    partial = tmp_path / "catalog.db.pre-0003.partial"
    partial.write_bytes(b"the copy")
    final = tmp_path / _COPY_NAME
    _rename_without_replacing(partial, final=final, link=_link_refused_with(code))
    assert final.read_bytes() == b"the copy"
    assert _copy_names(tmp_path) == [_COPY_NAME]


def test_a_taken_name_refuses_a_rename_where_hard_links_are_refused(tmp_path: Path) -> None:
    partial = tmp_path / "catalog.db.pre-0003.partial"
    partial.write_bytes(b"the copy")
    taken = tmp_path / _COPY_NAME
    taken.write_bytes(b"taken")
    with pytest.raises(MigrationError, match=rf"{_COPY_NAME} not created: File exists$"):
        _rename_without_replacing(partial, final=taken, link=_link_refused_with(errno.EPERM))
    assert taken.read_bytes() == b"taken"
    assert _copy_names(tmp_path) == [_COPY_NAME]


def test_a_copy_of_a_database_named_by_a_relative_path_is_reused(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    # A URI escapes these characters.
    path = tmp_path / "data #%?" / "catalog.db"
    _seeded(path, scripts=scripts).close()
    relative_path = Path(os.path.relpath(path))
    time = FakeTime()
    copier = _copier(time=time)
    with closing(
        database_opener().open(relative_path, scripts=scripts[: len(_SEED)])
    ) as connection:
        copier.ensure_copy(
            connection, path=relative_path, pending=_pending(scripts), open_reader=open_reader
        )
        time.advance(timedelta(minutes=1))
        copier.ensure_copy(
            connection, path=relative_path, pending=_pending(scripts), open_reader=open_reader
        )
    assert _copy_names(path.parent) == [_COPY_NAME]


def test_the_latest_copy_is_read_through_the_open_reader_given(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    opened: list[Path] = []

    def recording_open_reader(candidate: Path) -> sqlite3.Connection:
        opened.append(candidate)
        return open_reader(candidate)

    copier = _copier()
    with closing(_seeded(path, scripts=scripts)) as connection:
        copier.ensure_copy(
            connection, path=path, pending=_pending(scripts), open_reader=recording_open_reader
        )
        copier.ensure_copy(
            connection, path=path, pending=_pending(scripts), open_reader=recording_open_reader
        )
    assert opened == [path.parent / _COPY_NAME]


_FAILING = _COPY_BEFORE + "DELETE FROM t;\nINSERT INTO absent VALUES (1);"


def _open(path: Path, *, scripts: tuple[Migration, ...], copier: SqlitePreMigrationCopier) -> None:
    """An open over the scripts through ``copier``, then the connection closed."""
    SqliteDatabaseOpener(
        copier,
        ticker=FakeTicker(),
        free_bytes=FakeFreeBytes(_AMPLE_BYTES).free_bytes,
        memory_releaser=FakeMemoryReleaser(),
    ).open(path, scripts=scripts).close()


def test_a_block_failing_after_a_migration_succeeded_is_retried_on_the_same_copy(
    tmp_path: Path,
) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;", _FAILING)
    path = tmp_path / "data" / "catalog.db"
    _seeded(path, scripts=scripts).close()
    time = FakeTime()
    copier = _copier(time=time)
    with pytest.raises(MigrationError, match="migration 4"):
        _open(path, scripts=scripts, copier=copier)
    first = (path.parent / _COPY_NAME).stat()
    time.advance(timedelta(minutes=1))
    (path.parent / "catalog.db.pre-0003.partial").write_bytes(b"a copy a stop interrupted")
    with pytest.raises(MigrationError, match="migration 4"):
        _open(path, scripts=scripts, copier=copier)
    assert _copy_names(path.parent) == [_COPY_NAME]
    again = (path.parent / _COPY_NAME).stat()
    assert (again.st_ino, again.st_mtime_ns) == (first.st_ino, first.st_mtime_ns)


def test_a_changed_database_gets_a_new_copy(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _FAILING)
    path = tmp_path / "data" / "catalog.db"
    _seeded(path, scripts=scripts).close()
    time = FakeTime()
    copier = _copier(time=time)
    with pytest.raises(MigrationError, match="migration 3"):
        _open(path, scripts=scripts, copier=copier)
    first_bytes = (path.parent / _COPY_NAME).read_bytes()
    with closing(sqlite3.connect(path, autocommit=True)) as writer:
        writer.execute("INSERT INTO t VALUES (3)")
    time.advance(timedelta(minutes=1))
    with pytest.raises(MigrationError, match="migration 3"):
        _open(path, scripts=scripts, copier=copier)
    second_name = "catalog.db.pre-0003.2026-06-12_00-01-00_UTC"
    assert _copy_names(path.parent) == [_COPY_NAME, second_name]
    assert (path.parent / _COPY_NAME).read_bytes() == first_bytes


def test_an_unreadable_candidate_is_not_reused(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "scripts", _COPY_BEFORE + "DELETE FROM t;")
    path = tmp_path / "data" / "catalog.db"
    time = FakeTime()
    copier = _copier(time=time)
    junk = path.parent / "catalog.db.pre-0003.2026-06-12_00-01-00_UTC"
    with closing(_seeded(path, scripts=scripts)) as connection:
        copier.ensure_copy(
            connection, path=path, pending=_pending(scripts), open_reader=open_reader
        )
        junk.write_bytes(b"junk" * 1024)
        time.advance(timedelta(minutes=2))
        copier.ensure_copy(
            connection, path=path, pending=_pending(scripts), open_reader=open_reader
        )
    second_name = "catalog.db.pre-0003.2026-06-12_00-02-00_UTC"
    assert _copy_names(path.parent) == [_COPY_NAME, junk.name, second_name]
    assert junk.read_bytes() == b"junk" * 1024
