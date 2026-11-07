"""A migrated ``catalog.db`` or ``local.db``, or a read-only connection, through
``SqliteDatabaseOpener``, for a test that only needs an open database."""

import sqlite3
from functools import partial
from pathlib import Path
from typing import Protocol
from weakref import finalize

from p2pwatch.adapters.driven.persistence_sqlite.migration_scripts import PendingMigrations
from p2pwatch.adapters.driven.persistence_sqlite.reader_opener import ReaderOpener
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    SqliteDatabaseOpener,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_pre_migration_copier import (
    FreeBytesMeter,
    SqlitePreMigrationCopier,
)
from p2pwatch.application.ports.driven.memory_releaser import MemoryReleaser
from tests.fakes.adapters.driven.fake_free_bytes import FakeFreeBytes
from tests.fakes.adapters.driven.fake_memory_releaser import FakeMemoryReleaser
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


def database_opener(
    *, free_bytes: FreeBytesMeter | None = None, memory_releaser: MemoryReleaser | None = None
) -> SqliteDatabaseOpener:
    """An opener whose pre-migration copies are named from a ``FakeTime``, ticked by a
    ``FakeTicker`` and never short of space, unless ``free_bytes`` measures otherwise, releasing
    memory through a ``FakeMemoryReleaser`` unless ``memory_releaser`` is given."""
    free_bytes = free_bytes or FakeFreeBytes(_AMPLE_BYTES).free_bytes
    return SqliteDatabaseOpener(
        SqlitePreMigrationCopier(FakeTime().wall, ticker=FakeTicker(), free_bytes=free_bytes),
        ticker=FakeTicker(),
        free_bytes=free_bytes,
        memory_releaser=memory_releaser or FakeMemoryReleaser(),
    )


def database_opener_setting(
    pragma: str, *, free_bytes: FreeBytesMeter | None = None
) -> SqliteDatabaseOpener:
    """The same, ``pragma`` run on each connection before its migrations."""
    return SqliteDatabaseOpener(
        _PreparingCopier(lambda connection: connection.execute(pragma)),
        ticker=FakeTicker(),
        free_bytes=free_bytes or FakeFreeBytes(_AMPLE_BYTES).free_bytes,
        memory_releaser=FakeMemoryReleaser(),
    )


def database_opener_ticked_by(ticker: FakeTicker) -> SqliteDatabaseOpener:
    """The same, ticked by ``ticker``, which a migration script ticks by ``SELECT tick();``."""
    return SqliteDatabaseOpener(
        _PreparingCopier(lambda connection: connection.create_function("tick", 0, ticker.tick)),
        ticker=ticker,
        free_bytes=FakeFreeBytes(_AMPLE_BYTES).free_bytes,
        memory_releaser=FakeMemoryReleaser(),
    )


def database_opener_ticked_by_progress(ticker: FakeTicker) -> SqliteDatabaseOpener:
    """The same, ticked by ``ticker`` at each of SQLite's virtual machine instructions, a
    ``VACUUM``'s included."""
    return SqliteDatabaseOpener(
        _PreparingCopier(lambda connection: connection.set_progress_handler(ticker.tick, 1)),
        ticker=ticker,
        free_bytes=FakeFreeBytes(_AMPLE_BYTES).free_bytes,
        memory_releaser=FakeMemoryReleaser(),
    )


def database_opener_registering(function_name: str) -> SqliteDatabaseOpener:
    """The same, the SQL function ``function_name`` registered on each connection before its
    migrations, so that a test tells the connection that migrated from one opened after."""
    return SqliteDatabaseOpener(
        _PreparingCopier(lambda connection: connection.create_function(function_name, 0, int)),
        ticker=FakeTicker(),
        free_bytes=FakeFreeBytes(_AMPLE_BYTES).free_bytes,
        memory_releaser=FakeMemoryReleaser(),
    )


def _register_opening_on_release(
    connection: sqlite3.Connection, *, path: Path, holders: list[sqlite3.Connection]
) -> None:
    """Registers a SQL function on ``connection`` whose release opens a reader of ``path`` into
    ``holders``."""
    function = partial(int)
    finalize(function, _open_holder, path, holders=holders)
    connection.create_function("open_on_release", 0, function)


def _open_holder(path: Path, *, holders: list[sqlite3.Connection]) -> None:
    holder = open_reader(path)
    holder.execute("SELECT count(*) FROM sqlite_schema").fetchone()
    holders.append(holder)


def database_opener_held_at_reopen(
    path: Path, *, holders: list[sqlite3.Connection]
) -> SqliteDatabaseOpener:
    """The same, another connection reading ``path`` in the instant between the first connection's
    close and the reopen: SQLite releases a closed connection's functions once its file is."""
    return SqliteDatabaseOpener(
        _PreparingCopier(
            lambda connection: _register_opening_on_release(connection, path=path, holders=holders)
        ),
        ticker=FakeTicker(),
        free_bytes=FakeFreeBytes(_AMPLE_BYTES).free_bytes,
        memory_releaser=FakeMemoryReleaser(),
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
