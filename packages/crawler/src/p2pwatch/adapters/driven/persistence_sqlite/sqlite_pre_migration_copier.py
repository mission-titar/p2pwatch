"""Keeps a copy of a database, beside it, before a migration that rewrites its rows."""

import logging
import os
import sqlite3
from collections.abc import Callable
from datetime import UTC
from glob import escape
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite.connection import PendingMigrations
from p2pwatch.adapters.driven.persistence_sqlite.errors import MigrationError, wrap_sqlite_errors
from p2pwatch.application.ports.driven.wall_clock import WallClock

_logger = logging.getLogger(__name__)


class SqlitePreMigrationCopier:
    """Makes the pre-migration copy of a database, ``<file>.pre-<NNNN>.<instant>_UTC``, ``NNNN``
    its first pending version, and never deletes one."""

    def __init__(self, wall_clock: WallClock, free_bytes: Callable[[Path], int]) -> None:
        self._wall_clock = wall_clock
        self._free_bytes = free_bytes

    def ensure_copy(
        self, connection: sqlite3.Connection, path: Path, pending: PendingMigrations
    ) -> None:
        """On return, a pre-migration copy of ``path`` exists, or none was needed: no pending
        migration is marked ``copy-before``, or the database is new. Short of free space, it
        raises ``MigrationError`` before writing anything."""
        _delete_leftovers(path)
        if pending.current_version == 0 or not any(
            migration.copy_before for migration in pending.migrations
        ):
            return
        prefix = f"{path.name}.pre-{pending.migrations[0].version:04d}"
        with wrap_sqlite_errors():
            self._check_free_space(connection, path)
            partial = path.with_name(f"{prefix}.partial")
            _logger.info("pre-migration copy of %s: writing %s", path, partial)
            # Outside any transaction, which VACUUM INTO refuses.
            connection.execute("VACUUM INTO ?", (str(partial),))
        instant = self._wall_clock.now().astimezone(UTC).strftime("%Y-%m-%d_%H-%M-%S")
        _rename_without_replacing(partial, path.with_name(f"{prefix}.{instant}_UTC"))

    def _check_free_space(self, connection: sqlite3.Connection, path: Path) -> None:
        # The copy holds the live pages only; the migrations need the file's size again.
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
        freelist_count = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
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
    except FileExistsError as error:
        raise MigrationError(f"pre-migration copy: {final} already exists") from error
    finally:
        partial.unlink()
    _logger.info("pre-migration copy: %s", final)
