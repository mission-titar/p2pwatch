"""A migrated ``catalog.db`` or ``local.db``, or a read-only connection, through
``SqliteDatabaseOpener``, for a test that only needs an open database."""

import sqlite3
from pathlib import Path
from typing import Protocol

from p2pwatch.adapters.driven.persistence_sqlite.migration_scripts import PendingMigrations
from p2pwatch.adapters.driven.persistence_sqlite.reader_opener import ReaderOpener
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    SqliteDatabaseOpener,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_pre_migration_copier import (
    FreeBytesMeter,
    SqlitePreMigrationCopier,
)
from tests.fakes.adapters.driven.fake_free_bytes import FakeFreeBytes
from tests.fakes.adapters.driven.fake_ticker import FakeTicker
from tests.fakes.adapters.driven.fake_time import FakeTime

_AMPLE_BYTES = 1 << 62


class _Preparation(Protocol):
    def __call__(self, connection: sqlite3.Connection, /) -> object: ...


class _PreparingCopier(SqlitePreMigrationCopier):
    """Prepares each connection where the opener calls its copier: once the connection is
    configured, before the migrations."""

    def __init__(self, prepare: _Preparation) -> None:
        super().__init__(
            FakeTime().wall, ticker=FakeTicker(), free_bytes=FakeFreeBytes(_AMPLE_BYTES).free_bytes
        )
        self._prepare = prepare

    def ensure_copy(
        self,
        connection: sqlite3.Connection,
        *,
        path: Path,
        pending: PendingMigrations,
        open_reader: ReaderOpener,
    ) -> None:
        self._prepare(connection)
        super().ensure_copy(connection, path=path, pending=pending, open_reader=open_reader)


def database_opener(*, free_bytes: FreeBytesMeter | None = None) -> SqliteDatabaseOpener:
    """An opener whose pre-migration copies are named from a ``FakeTime``, ticked by a
    ``FakeTicker`` and never short of space, unless ``free_bytes`` measures otherwise."""
    free_bytes = free_bytes or FakeFreeBytes(_AMPLE_BYTES).free_bytes
    return SqliteDatabaseOpener(
        SqlitePreMigrationCopier(FakeTime().wall, ticker=FakeTicker(), free_bytes=free_bytes),
        ticker=FakeTicker(),
        free_bytes=free_bytes,
    )


def database_opener_setting(
    pragma: str, *, free_bytes: FreeBytesMeter | None = None
) -> SqliteDatabaseOpener:
    """The same, ``pragma`` run on each connection before its migrations."""
    return SqliteDatabaseOpener(
        _PreparingCopier(lambda connection: connection.execute(pragma)),
        ticker=FakeTicker(),
        free_bytes=free_bytes or FakeFreeBytes(_AMPLE_BYTES).free_bytes,
    )


def database_opener_ticked_by(ticker: FakeTicker) -> SqliteDatabaseOpener:
    """The same, ticked by ``ticker``, which a migration script ticks by ``SELECT tick();``."""
    return SqliteDatabaseOpener(
        _PreparingCopier(lambda connection: connection.create_function("tick", 0, ticker.tick)),
        ticker=ticker,
        free_bytes=FakeFreeBytes(_AMPLE_BYTES).free_bytes,
    )


def open_catalog(path: Path) -> sqlite3.Connection:
    """Opens/migrates ``catalog.db``."""
    return database_opener().open_catalog(path)


def open_local(path: Path) -> sqlite3.Connection:
    """Opens/migrates ``local.db``."""
    return database_opener().open_local(path)


def open_reader(path: Path) -> sqlite3.Connection:
    """Opens ``path`` read-only."""
    return database_opener().open_reader(path)
