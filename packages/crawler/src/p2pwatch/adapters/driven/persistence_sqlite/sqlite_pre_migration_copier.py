"""Keeps a copy of a database, beside it, before a migration that rewrites its rows."""

import errno
import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, timedelta
from glob import escape
from pathlib import Path
from typing import Protocol

from p2pwatch.adapters.driven.persistence_sqlite.database_digest import database_digest
from p2pwatch.adapters.driven.persistence_sqlite.errors import (
    MigrationError,
    OpeningInterruptedError,
    PersistenceError,
    wrap_sqlite_errors,
)
from p2pwatch.adapters.driven.persistence_sqlite.migration_scripts import PendingMigrations
from p2pwatch.adapters.driven.persistence_sqlite.reader_opener import ReaderOpener
from p2pwatch.application.ports.driven.ticker import Ticker
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.domain.gigabytes import gigabytes
from p2pwatch.domain.inaccessible_path_error import InaccessiblePathError
from p2pwatch.domain.out_of_space_error import OutOfSpaceError

_logger = logging.getLogger(__name__)
# Under a minute between two lines: a silent start is one an operator restarts.
_PROGRESS_PERIOD = timedelta(seconds=30)


class Linker(Protocol):
    def __call__(self, source: Path, destination: Path, /) -> None: ...  # noqa: PLR0917


# What a filesystem refusing hard links answers (EPERM: vfat, some FUSE and network mounts).
_LINK_REFUSED = frozenset({errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP})


# The free bytes of the filesystem holding ``path``, else ``InaccessiblePathError``.
class FreeBytesMeter(Protocol):
    def __call__(self, path: Path, /) -> int: ...


class SqlitePreMigrationCopier:
    """Makes the pre-migration copy of a database, ``<file>.pre-<NNNN>.<stamp>_UTC``, ``NNNN``
    its first pending version, and never deletes one."""

    def __init__(
        self, wall_clock: WallClock, *, ticker: Ticker, free_bytes: FreeBytesMeter
    ) -> None:
        self._wall_clock = wall_clock
        self._ticker = ticker
        self._free_bytes = free_bytes

    def ensure_copy(
        self,
        connection: sqlite3.Connection,
        *,
        path: Path,
        pending: PendingMigrations,
        open_reader: ReaderOpener,
    ) -> None:
        """On return, a pre-migration copy matching ``path``'s content exists, reused or made, or
        none was needed: no pending migration is marked ``copy-before``, or the database is new.
        The latest copy is read through ``open_reader``. Short of free space, it raises
        ``OutOfSpaceError`` before writing anything; a file it cannot read or write,
        ``MigrationError``; a statement interrupted by the connection's progress handler, the
        comparison's or the copy's, ``OpeningInterruptedError``."""
        try:
            self._ensure_copy(connection, path=path, pending=pending, open_reader=open_reader)
        except (OSError, InaccessiblePathError) as error:
            raise MigrationError(f"pre-migration copy of {path} failed: {error}") from error

    def _ensure_copy(
        self,
        connection: sqlite3.Connection,
        *,
        path: Path,
        pending: PendingMigrations,
        open_reader: ReaderOpener,
    ) -> None:
        _delete_leftovers(path)
        if pending.current_version == 0 or not any(
            migration.copy_before for migration in pending.migrations
        ):
            return
        prefix = f"{path.name}.pre-{pending.migrations[0].version:04d}"
        with wrap_sqlite_errors(), _interruption_as_a_stop(path, version=pending.current_version):
            if self._matches_its_latest_copy(
                connection, path=path, prefix=prefix, open_reader=open_reader
            ):
                return
            live_bytes = _live_bytes(connection)
            self._check_free_space(path=path, live_bytes=live_bytes)
            partial = path.with_name(f"{prefix}.partial")
            _logger.info(
                "pre-migration copy of %s: writing %s to %s; a stop now costs only the time spent",
                path,
                gigabytes(live_bytes),
                partial,
            )

            def report_written(*, elapsed: timedelta) -> None:
                written_bytes = _size_or_zero(partial)
                _logger.info(
                    "pre-migration copy of %s: %s of %s written (%d %%)",
                    path,
                    gigabytes(written_bytes),
                    gigabytes(live_bytes),
                    written_bytes * 100 // live_bytes,
                )

            self._ticker.run(
                # Outside any transaction, which VACUUM INTO refuses.
                lambda: connection.execute("VACUUM INTO ?", (str(partial),)),
                tick=report_written,
                period=_PROGRESS_PERIOD,
            )
        stamp = self._wall_clock.now().astimezone(UTC).strftime("%Y-%m-%d_%H-%M-%S")
        _rename_without_replacing(partial, final=path.with_name(f"{prefix}.{stamp}_UTC"))

    def _check_free_space(self, *, path: Path, live_bytes: int) -> None:
        # The copy holds the live pages only; the migrations need the file's size again.
        # A connection in WAL mode keeps its -wal while it is open.
        wal_bytes = Path(f"{path}-wal").stat().st_size
        copy_bytes = live_bytes + wal_bytes
        need_bytes = copy_bytes + path.stat().st_size + wal_bytes
        free_bytes = self._free_bytes(path.parent)
        if free_bytes < need_bytes:
            raise OutOfSpaceError(
                step=f"pre-migration copy of {path}",
                directory=path.parent,
                free_bytes=free_bytes,
                need_bytes=need_bytes,
                outcome="nothing written",
            )

    def _matches_its_latest_copy(
        self,
        connection: sqlite3.Connection,
        *,
        path: Path,
        prefix: str,
        open_reader: ReaderOpener,
    ) -> bool:
        """Whether the most recent ``<prefix>.*_UTC`` holds the database's content."""
        candidates = sorted(path.parent.glob(escape(prefix) + ".*_UTC"))
        if not candidates:
            return False
        latest = candidates[-1]
        _logger.info(
            "pre-migration copy of %s: comparing with %s, the copy an earlier start made, to "
            "reuse it if it still matches; a stop now costs only the time spent",
            path,
            latest,
        )

        def report_elapsed(*, elapsed: timedelta) -> None:
            _logger.info(
                "pre-migration copy of %s: comparing, %d s elapsed", path, elapsed.total_seconds()
            )

        if not self._ticker.run(
            lambda: _same_content(connection, copy=latest, open_reader=open_reader),
            tick=report_elapsed,
            period=_PROGRESS_PERIOD,
        ):
            return False
        _logger.info("pre-migration copy of %s: reusing %s", path, latest)
        return True


def _same_content(connection: sqlite3.Connection, *, copy: Path, open_reader: ReaderOpener) -> bool:
    """Whether ``copy`` holds the content of ``connection``'s database; a copy that cannot be read
    matches nothing and is left alone."""
    try:
        with closing(open_reader(copy)) as candidate:
            candidate_digest = database_digest(candidate)
    except (sqlite3.Error, PersistenceError) as error:
        if isinstance(error, sqlite3.Error) and error.sqlite_errorcode == sqlite3.SQLITE_INTERRUPT:
            raise
        _logger.warning("pre-migration copy: %s cannot be read (%s)", copy, error)
        return False
    return candidate_digest == database_digest(connection)


@contextmanager
def _interruption_as_a_stop(path: Path, *, version: int) -> Iterator[None]:
    try:
        yield
    except sqlite3.Error as error:
        if error.sqlite_errorcode == sqlite3.SQLITE_INTERRUPT:
            raise OpeningInterruptedError(
                f"the pre-migration copy of {path} stopped, the database at version {version}"
            ) from error
        raise


def _live_bytes(connection: sqlite3.Connection) -> int:
    """The bytes of the pages the database uses, which its copy holds."""
    page_size = int(connection.execute("PRAGMA page_size").fetchone()["page_size"])
    page_count = int(connection.execute("PRAGMA page_count").fetchone()["page_count"])
    freelist_count = int(connection.execute("PRAGMA freelist_count").fetchone()["freelist_count"])
    return (page_count - freelist_count) * page_size


def _size_or_zero(path: Path) -> int:
    """``path``'s size, 0 before it exists."""
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _delete_leftovers(path: Path) -> None:
    """Deletes the copies a stop interrupted, and their journals: ``VACUUM INTO`` refuses an
    existing file."""
    for partial in path.parent.glob(escape(path.name) + ".pre-*.partial"):
        _logger.info(
            "pre-migration copy of %s: the previous start's copy was interrupted, deleting %s; "
            "the copy starts over",
            path,
            partial,
        )
        partial.unlink()
    for journal in path.parent.glob(escape(path.name) + ".pre-*.partial-journal"):
        journal.unlink()


def _rename_without_replacing(partial: Path, *, final: Path, link: Linker = os.link) -> None:
    # os.rename and os.replace would silently replace a file at the final name.
    try:
        try:
            link(partial, final)
        except OSError as error:
            if error.errno not in _LINK_REFUSED:
                raise
            # Only one opener writes a database's copies, and their names carry the second.
            if final.exists():
                raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST)) from error
            os.rename(partial, final)
    except OSError as error:
        raise MigrationError(
            f"pre-migration copy: {final} not created: {error.strerror}"
        ) from error
    finally:
        partial.unlink(missing_ok=True)
    _logger.info("pre-migration copy: %s", final)
