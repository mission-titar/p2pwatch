"""Keeps a copy of a database, beside it, before a migration that rewrites its rows."""

import logging
import os
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC
from glob import escape
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite.database_digest import database_digest
from p2pwatch.adapters.driven.persistence_sqlite.errors import MigrationError, wrap_sqlite_errors
from p2pwatch.adapters.driven.persistence_sqlite.migration_scripts import PendingMigrations
from p2pwatch.application.ports.driven.wall_clock import WallClock

_logger = logging.getLogger(__name__)


class SqlitePreMigrationCopier:
    """Makes the pre-migration copy of a database, ``<file>.pre-<NNNN>.<stamp>_UTC``, ``NNNN``
    its first pending version, and never deletes one."""

    def __init__(self, wall_clock: WallClock, free_bytes: Callable[[Path], int]) -> None:
        self._wall_clock = wall_clock
        self._free_bytes = free_bytes

    def ensure_copy(
        self,
        connection: sqlite3.Connection,
        path: Path,
        pending: PendingMigrations,
        open_reader: Callable[[Path], sqlite3.Connection],
    ) -> None:
        """On return, a pre-migration copy matching ``path``'s content exists, reused or made, or
        none was needed: no pending migration is marked ``copy-before``, or the database is new.
        The latest copy is read through ``open_reader``. Short of free space, it raises
        ``MigrationError`` before writing anything."""
        _delete_leftovers(path)
        if pending.current_version == 0 or not any(
            migration.copy_before for migration in pending.migrations
        ):
            return
        prefix = f"{path.name}.pre-{pending.migrations[0].version:04d}"
        with wrap_sqlite_errors():
            if _matches_its_latest_copy(connection, path, prefix, open_reader):
                return
            self._check_free_space(connection, path)
            partial = path.with_name(f"{prefix}.partial")
            _logger.info("pre-migration copy of %s: writing %s", path, partial)
            # Outside any transaction, which VACUUM INTO refuses.
            connection.execute("VACUUM INTO ?", (str(partial),))
        stamp = self._wall_clock.now().astimezone(UTC).strftime("%Y-%m-%d_%H-%M-%S")
        _rename_without_replacing(partial, path.with_name(f"{prefix}.{stamp}_UTC"))

    def _check_free_space(self, connection: sqlite3.Connection, path: Path) -> None:
        # The copy holds the live pages only; the migrations need the file's size again.
        page_size = int(connection.execute("PRAGMA page_size").fetchone()["page_size"])
        page_count = int(connection.execute("PRAGMA page_count").fetchone()["page_count"])
        freelist_count = int(
            connection.execute("PRAGMA freelist_count").fetchone()["freelist_count"]
        )
        # A connection in WAL mode keeps its -wal while it is open.
        wal_bytes = Path(f"{path}-wal").stat().st_size
        copy_bytes = (page_count - freelist_count) * page_size + wal_bytes
        need_bytes = copy_bytes + path.stat().st_size + wal_bytes
        free_bytes = self._free_bytes(path.parent)
        if free_bytes < need_bytes:
            raise MigrationError(
                f"pre-migration copy of {path}: {need_bytes} bytes needed in {path.parent}, "
                f"{free_bytes} free"
            )


def _matches_its_latest_copy(
    connection: sqlite3.Connection,
    path: Path,
    prefix: str,
    open_reader: Callable[[Path], sqlite3.Connection],
) -> bool:
    """Whether the most recent ``<prefix>.*_UTC`` holds the database's content; one that cannot
    be read matches nothing and is left alone."""
    candidates = sorted(path.parent.glob(escape(prefix) + ".*_UTC"))
    if not candidates:
        return False
    latest = candidates[-1]
    _logger.info("pre-migration copy of %s: comparing with %s", path, latest)
    try:
        with closing(open_reader(latest)) as candidate:
            candidate_digest = database_digest(candidate)
    except sqlite3.Error as error:
        _logger.warning("pre-migration copy: %s cannot be read (%s)", latest, error)
        return False
    if candidate_digest != database_digest(connection):
        return False
    _logger.info("pre-migration copy of %s: reusing %s", path, latest)
    return True


def _delete_leftovers(path: Path) -> None:
    """Deletes the copies a stop interrupted, and their journals: ``VACUUM INTO`` refuses an
    existing file."""
    for pattern in (".pre-*.partial", ".pre-*.partial-journal"):
        for leftover in path.parent.glob(escape(path.name) + pattern):
            leftover.unlink()


def _rename_without_replacing(partial: Path, final: Path) -> None:
    # os.rename and os.replace would silently replace a file at the final name.
    try:
        os.link(partial, final)
    except OSError as error:
        raise MigrationError(
            f"pre-migration copy: {final} not created: {error.strerror}"
        ) from error
    finally:
        partial.unlink()
    _logger.info("pre-migration copy: %s", final)
