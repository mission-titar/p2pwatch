"""Opens every SQLite connection: ``catalog.db`` and ``local.db``, each migrated to the code's
version, the read-only readers, and an empty one in memory; each reads its rows by column name, the
factory private here, and opens a URI, so that it can attach a database read-only.

Each connection is opened in REAL autocommit (``autocommit=True``, Python ≥ 3.12):
transactions are EXPLICIT (``BEGIN``/``COMMIT``/``ROLLBACK`` written by the
stores), no implicit isolation. Opening PRAGMAs (spec §3):
``journal_mode=WAL`` - REQUIRED: ``:memory:`` does not carry it (it answers ``memory``)
and is therefore refused by ``open``; the tests use real files (spec §8) -
``foreign_keys=ON``, and ``recursive_triggers=ON`` (without which ``INSERT OR REPLACE``
crosses the append-only triggers, spec §3 post-review amendment).

The steps of an open are private: nothing else can migrate a database without its pre-migration
copy.
"""

import logging
import sqlite3
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta
from importlib import resources
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

from p2pwatch.adapters.driven.persistence_sqlite.errors import (
    MigrationError,
    OpeningInterruptedError,
    PersistenceError,
    wrap_sqlite_errors,
)
from p2pwatch.adapters.driven.persistence_sqlite.migration_scripts import (
    Migration,
    PendingMigrations,
    load_scripts,
)
from p2pwatch.adapters.driven.persistence_sqlite.named_row import NamedRow
from p2pwatch.adapters.driven.persistence_sqlite.search_fold import fold_for_search
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_pre_migration_copier import (
    FreeBytesMeter,
    SqlitePreMigrationCopier,
)
from p2pwatch.adapters.driven.persistence_sqlite.variants import (
    SqlFunctionFailures,
    register_sql_functions,
    remove_migration_sql_functions,
)
from p2pwatch.application.ports.driven.memory_releaser import MemoryReleaser
from p2pwatch.application.ports.driven.ticker import Ticker
from p2pwatch.domain.gigabytes import gigabytes
from p2pwatch.domain.held_database_error import HeldDatabaseError
from p2pwatch.domain.inaccessible_path_error import InaccessiblePathError
from p2pwatch.domain.out_of_space_error import OutOfSpaceError

_logger = logging.getLogger(__name__)

_MIGRATIONS = resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations"
# Under a minute between two lines: a silent start is one an operator restarts.
_PROGRESS_PERIOD = timedelta(seconds=30)
_BUSY_TIMEOUT_SECONDS = 5.0  # Python's default, which the crawler has always had
# How many SQLite VM steps the block runs between two reads of the shutdown check.
_SHUTDOWN_CHECK_INSTRUCTIONS = 1000


# Whether the shutdown was requested, read on the opening's thread, between its steps.
class ShutdownCheck(Protocol):
    def __call__(self) -> bool: ...


class SqliteDatabaseOpener:
    """Opens a database and applies its pending migrations, the one way the code migrates one, or
    opens a reader of it."""

    def __init__(
        self,
        pre_migration_copier: SqlitePreMigrationCopier,
        *,
        ticker: Ticker,
        free_bytes: FreeBytesMeter,
        memory_releaser: MemoryReleaser,
        shutdown_requested: ShutdownCheck,
    ) -> None:
        self._pre_migration_copier = pre_migration_copier
        self._shutdown_requested = shutdown_requested
        self._ticker = ticker
        self._free_bytes = free_bytes
        self._memory_releaser = memory_releaser

    def open_catalog(self, path: Path, *, exclusive: bool = False) -> sqlite3.Connection:
        """Opens/migrates ``catalog.db`` (the append-only triggers are part of the schema);
        ``exclusive``, see ``open``."""
        return self.open(path, scripts=load_scripts(_MIGRATIONS / "catalog"), exclusive=exclusive)

    def open_local(self, path: Path) -> sqlite3.Connection:
        """Opens/migrates ``local.db``."""
        return self.open(path, scripts=load_scripts(_MIGRATIONS / "local"))

    def catalog_version(self) -> int:
        """The schema version ``open_catalog`` brings a catalog to."""
        return _latest_version(load_scripts(_MIGRATIONS / "catalog"))

    def open(
        self, path: Path, *, scripts: tuple[Migration, ...], exclusive: bool = False
    ) -> sqlite3.Connection:
        """Opens ``path`` and applies the ``scripts`` above its version, after its pre-migration
        copy, then opens it again and releases the memory the block took; gives back its free
        pages once they are a quarter of the file. A database newer than the ``scripts`` raises
        ``MigrationError``, a lack of disk space ``OutOfSpaceError``, a requested shutdown
        ``OpeningInterruptedError`` before the block, during it or after it. ``exclusive``, each
        connection holds ``path`` until it closes, and another one raises ``HeldDatabaseError``, at
        the reopen too, the database then migrated."""
        failures = SqlFunctionFailures()
        connection = _connect(path, exclusive=exclusive, failures=failures)
        try:
            pending = _pending_migrations(connection, scripts=scripts)
            self._pre_migration_copier.ensure_copy(
                connection, path=path, pending=pending, open_reader=self.open_reader
            )
            self._stop_if_requested(path, version=pending.current_version)
            with wrap_sqlite_errors():
                # On disk: an in-memory sort is unbounded (+697 MB for one index at 11.5M rows), and
                # VACUUM builds its whole copy in a temporary database.
                connection.execute("PRAGMA temp_store=FILE")
            _apply_migrations(
                connection,
                path=path,
                pending=pending,
                ticker=self._ticker,
                free_bytes=self._free_bytes,
                failures=failures,
                shutdown_requested=self._shutdown_requested,
            )
            if pending.migrations:
                # Closed, it drops the memos, the page cache and the pragmas the scripts set.
                connection.close()
                connection = _connect(path, exclusive=exclusive, failures=failures)
                with wrap_sqlite_errors():
                    connection.execute("PRAGMA temp_store=FILE")
                self._stop_if_requested(path, version=pending.migrations[-1].version)
            _reclaim(connection, path=path, ticker=self._ticker, free_bytes=self._free_bytes)
            with wrap_sqlite_errors():
                connection.execute("PRAGMA temp_store=DEFAULT")
                remove_migration_sql_functions(connection)
            if pending.migrations:
                # The C library keeps what the closed connection freed: 280 MB after a 4.x upgrade.
                self._memory_releaser.release()
        except BaseException:
            # Unconditional close: whatever fails, the connection must not leak.
            connection.close()
            raise
        return connection

    def _stop_if_requested(self, path: Path, *, version: int) -> None:
        if self._shutdown_requested():
            raise OpeningInterruptedError(
                f"the opening of {path} stopped, the database at version {version}"
            )

    def open_reader(self, path: Path) -> sqlite3.Connection:
        """Opens ``path`` read-only, ``query_only``, its rows read by column name, its temporary
        b-trees on disk, ``fold_for_search`` registered, for the thread that opens it alone."""
        with wrap_sqlite_errors():
            connection = sqlite3.connect(read_only_uri(path), uri=True)
            connection.row_factory = _build_named_row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA temp_store=FILE")  # on disk: a sort in memory is unbounded
            # Not register_sql_functions: its memoized ones grow unbounded on the console's reader.
            connection.create_function("fold_for_search", 1, fold_for_search, deterministic=True)
        return connection

    def open_in_memory(self) -> sqlite3.Connection:
        """Opens an empty database in memory, its rows read by column name, to attach the
        databases a check reads."""
        connection = sqlite3.connect(":memory:", autocommit=True, uri=True)
        connection.row_factory = _build_named_row
        return connection


def read_only_uri(path: Path) -> str:
    """``path`` as the URI SQLite opens, or attaches, read-only."""
    # Not as_uri(), which refuses a relative path.
    return f"file:{quote(str(path))}?mode=ro"


def _connect(path: Path, *, exclusive: bool, failures: SqlFunctionFailures) -> sqlite3.Connection:
    """A connection to ``path`` in WAL, its rows read by column name, its pragmas set and the SQL
    functions registered, their failed calls kept in ``failures``; ``exclusive``, it holds
    ``path`` from its first access until it closes, refused at once beside another connection."""
    with wrap_sqlite_errors():
        connection = sqlite3.connect(
            f"file:{quote(str(path))}",
            autocommit=True,
            uri=True,
            timeout=0 if exclusive else _BUSY_TIMEOUT_SECONDS,
        )
    connection.row_factory = _build_named_row
    try:
        if exclusive:
            with wrap_sqlite_errors():
                # main alone: a bare locking_mode also holds every database attached later.
                connection.execute("PRAGMA main.locking_mode=EXCLUSIVE")
        _configure(connection, path=path)
        with wrap_sqlite_errors():
            register_sql_functions(connection, failures=failures)
    except BaseException:
        # Unconditional close: whatever fails, the connection must not leak.
        connection.close()
        raise
    return connection


def _build_named_row(cursor: sqlite3.Cursor, values: tuple[Any, ...]) -> NamedRow:  # noqa: PLR0917
    """The row factory: refuses a column name that appears twice, which a dict would keep once."""
    names = [column[0] for column in cursor.description]
    for name in names:
        if names.count(name) > 1:
            raise ValueError(f"the column {name!r} appears twice")
    return NamedRow(zip(names, values, strict=True))


def _configure(connection: sqlite3.Connection, *, path: Path) -> None:
    try:
        # The first access, where another connection's hold refuses an exclusive one.
        journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()["journal_mode"]
    except sqlite3.Error as error:
        if error.sqlite_errorcode == sqlite3.SQLITE_BUSY:
            raise HeldDatabaseError(f"{path} is held by another process") from error
        raise PersistenceError(str(error)) from error
    if journal_mode != "wal":
        raise PersistenceError(
            f"journal_mode={journal_mode!r}: WAL required (spec §3), file-backed db only"
        )
    with wrap_sqlite_errors():
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA recursive_triggers=ON")


def _pending_migrations(
    connection: sqlite3.Connection, *, scripts: tuple[Migration, ...]
) -> PendingMigrations:
    """The scripts above the database's ``user_version``; a database newer than the code raises
    ``MigrationError``."""
    with wrap_sqlite_errors():
        current_version = int(connection.execute("PRAGMA user_version").fetchone()["user_version"])
    latest = _latest_version(scripts)
    if current_version > latest:
        raise MigrationError(
            f"db at version {current_version}, code at version {latest}: "
            "db newer than the code, refusing to start (spec §3)"
        )
    migrations = tuple(migration for migration in scripts if migration.version > current_version)
    return PendingMigrations(current_version=current_version, migrations=migrations)


def _latest_version(scripts: tuple[Migration, ...]) -> int:
    return scripts[-1].version if scripts else 0


def _apply_migrations(
    connection: sqlite3.Connection,
    *,
    path: Path,
    pending: PendingMigrations,
    ticker: Ticker,
    free_bytes: FreeBytesMeter,
    failures: SqlFunctionFailures,
    shutdown_requested: ShutdownCheck,
) -> None:
    """Applies the pending scripts in order in one transaction, the schema version written once,
    at its end, a failure naming the SQL function call that raised it, a requested shutdown
    interrupting it; the rules for writing one: ``docs/contributing/architecture.md``, "Écrire
    une migration"."""
    if not pending.migrations:
        return
    _logger.info(
        "migrations of %s: from version %d to version %d in one step; "
        "a stop now rolls them back, costing only the time spent",
        path,
        pending.current_version,
        pending.migrations[-1].version,
    )
    step = _BlockStep()

    def report_running(*, elapsed: timedelta) -> None:
        _logger.info(
            "migrations of %s: %s running, %d s since the block began",
            path,
            step.name,
            elapsed.total_seconds(),
        )

    # The signal handler runs at the check's own call, inside the block's statements. Left set:
    # the open closes this connection after the block, whatever its end.
    connection.set_progress_handler(shutdown_requested, _SHUTDOWN_CHECK_INSTRUCTIONS)
    # No finally: a failed block fails the open, which closes the connection.
    try:
        ticker.run(
            lambda: _run_in_one_transaction(connection, migrations=pending.migrations, step=step),
            tick=report_running,
            period=_PROGRESS_PERIOD,
        )
    except sqlite3.Error as error:
        if error.sqlite_errorcode == sqlite3.SQLITE_INTERRUPT:
            raise OpeningInterruptedError(
                f"the migrations of {path} rolled back at {step.name}, "
                f"the database left at version {pending.current_version}"
            ) from error
        raise _migration_error(
            error,
            connection=connection,
            # A failed call aborts its statement, so the latest one kept is this error's.
            message=f"{step.name} failed: {failures.latest or error}",
            step=f"migrations of {path} ({step.name})",
            outcome=f"the database left at version {pending.current_version}",
            path=path,
            free_bytes=free_bytes,
        ) from error


@dataclass(kw_only=True)
class _BlockStep:
    """The step of the block running, which the ticker's thread reads for its line."""

    name: str = "the block's start"


def _run_in_one_transaction(
    connection: sqlite3.Connection, *, migrations: tuple[Migration, ...], step: _BlockStep
) -> None:
    # Two concurrent opens: the loser fails cleanly, single writer by doctrine.
    try:
        connection.execute("BEGIN")
        for migration in migrations:
            step.name = f"migration {migration.version}"
            _logger.info("migration %d: applying", migration.version)
            connection.executescript(migration.script)
            if not connection.in_transaction:
                raise MigrationError(
                    f"{step.name}: the script closed the migrations' transaction "
                    "(COMMIT/ROLLBACK forbidden inside a migration script)"
                )
        step.name = f"the commit at version {migrations[-1].version}"
        connection.execute(f"PRAGMA user_version = {migrations[-1].version}")
        connection.execute("COMMIT")
    except sqlite3.Error:
        with suppress(sqlite3.Error):
            connection.execute("ROLLBACK")
        raise


def _reclaim(
    connection: sqlite3.Connection,
    *,
    path: Path,
    ticker: Ticker,
    free_bytes: FreeBytesMeter,
) -> None:
    """Gives back the free pages once they are a quarter of the file: an upgrade frees that much,
    an ordinary catalog, which only grows, never does, and an interrupted reclaim runs again."""
    with wrap_sqlite_errors():
        page_size = int(connection.execute("PRAGMA page_size").fetchone()["page_size"])
        page_count = int(connection.execute("PRAGMA page_count").fetchone()["page_count"])
        freelist_count = int(
            connection.execute("PRAGMA freelist_count").fetchone()["freelist_count"]
        )
        version = int(connection.execute("PRAGMA user_version").fetchone()["user_version"])
    if freelist_count * 4 < page_count:
        return
    _logger.info(
        "reclaim of %s: giving back %s of free pages, %d %% of the file; "
        "a stop now costs only the time spent",
        path,
        gigabytes(freelist_count * page_size),
        freelist_count * 100 // page_count,
    )

    def report_running(*, elapsed: timedelta) -> None:
        _logger.info(
            "reclaim of %s: giving back free pages, %d s elapsed", path, elapsed.total_seconds()
        )

    try:
        ticker.run(lambda: _vacuum(connection), tick=report_running, period=_PROGRESS_PERIOD)
    except sqlite3.Error as error:
        raise _migration_error(
            error,
            connection=connection,
            message=f"reclaim failed: {error}",
            step=f"reclaim of {path}",
            outcome=f"the database at version {version}, its free pages not given back",
            path=path,
            free_bytes=free_bytes,
        ) from error


def _vacuum(connection: sqlite3.Connection) -> None:
    # Outside any transaction, which VACUUM requires.
    connection.execute("VACUUM")
    # The crawler holds its connection for good, so the WAL the VACUUM grew would never shrink.
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _migration_error(  # noqa: PLR0913
    cause: sqlite3.Error,
    *,
    connection: sqlite3.Connection,
    message: str,
    step: str,
    outcome: str,
    path: Path,
    free_bytes: FreeBytesMeter,
) -> MigrationError | OutOfSpaceError:
    """``OutOfSpaceError`` for a full disk, a ``MigrationError`` saying so when its free space
    cannot be measured, ``message``'s otherwise."""
    if cause.sqlite_errorcode == sqlite3.SQLITE_FULL:
        # The rolled-back frames would count as space taken until the connection closes.
        with suppress(sqlite3.Error):
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        try:
            free = free_bytes(path.parent)
        except InaccessiblePathError as error:
            return MigrationError(f"{step}: out of space in {path.parent}, {error}; {outcome}")
        return OutOfSpaceError(
            step=step, directory=path.parent, free_bytes=free, need_bytes=None, outcome=outcome
        )
    return MigrationError(message)
