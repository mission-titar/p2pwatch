"""Opens every SQLite connection: ``catalog.db`` and ``local.db``, each migrated to the code's
version, and the read-only readers; each reads its rows by column name, the factory private here.

Each connection is opened in REAL autocommit (``autocommit=True``, Python ≥ 3.12):
transactions are EXPLICIT (``BEGIN``/``COMMIT``/``ROLLBACK`` written by the
stores), no implicit isolation. Opening PRAGMAs (spec §3):
``journal_mode=WAL`` - REQUIRED: ``:memory:`` does not carry it (it answers ``memory``)
and is therefore refused outright; the tests use real files (spec §8) -
``foreign_keys=ON``, and ``recursive_triggers=ON`` (without which ``INSERT OR REPLACE``
crosses the append-only triggers, spec §3 post-review amendment).

The steps of an open are private: nothing else can migrate a database without its pre-migration
copy.
"""

import logging
import sqlite3
from contextlib import suppress
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import quote

from p2pwatch.adapters.driven.persistence_sqlite.errors import (
    MigrationError,
    PersistenceError,
    wrap_sqlite_errors,
)
from p2pwatch.adapters.driven.persistence_sqlite.migration_scripts import (
    Migration,
    PendingMigrations,
    load_scripts,
)
from p2pwatch.adapters.driven.persistence_sqlite.named_row import NamedRow
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_pre_migration_copier import (
    SqlitePreMigrationCopier,
)
from p2pwatch.adapters.driven.persistence_sqlite.variants import (
    register_sql_functions,
    remove_migration_sql_functions,
)

_logger = logging.getLogger(__name__)

_MIGRATIONS = resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations"
# Index = the value ``PRAGMA secure_delete`` reads; ``= 2`` would set ON, not FAST.
_SECURE_DELETE_MODES = ("OFF", "ON", "FAST")


class SqliteDatabaseOpener:
    """Opens a database and applies its pending migrations, the one way the code migrates one, or
    opens a reader of it."""

    def __init__(self, pre_migration_copier: SqlitePreMigrationCopier) -> None:
        self._pre_migration_copier = pre_migration_copier

    def open_catalog(self, path: Path) -> sqlite3.Connection:
        """Opens/migrates ``catalog.db`` (the append-only triggers are part of the schema)."""
        return self.open(path, scripts=load_scripts(_MIGRATIONS / "catalog"))

    def open_local(self, path: Path) -> sqlite3.Connection:
        """Opens/migrates ``local.db``."""
        return self.open(path, scripts=load_scripts(_MIGRATIONS / "local"))

    def open(self, path: Path, *, scripts: tuple[Migration, ...]) -> sqlite3.Connection:
        """Opens ``path`` and applies the ``scripts`` above its version, after its pre-migration
        copy; a database newer than the ``scripts`` raises ``MigrationError``."""
        connection = _connect(path)
        try:
            pending = _pending_migrations(connection, scripts=scripts)
            self._pre_migration_copier.ensure_copy(
                connection, path=path, pending=pending, open_reader=self.open_reader
            )
            _apply_migrations(connection, pending=pending)
            with wrap_sqlite_errors():
                remove_migration_sql_functions(connection)
        except BaseException:
            # Unconditional close: whatever fails, the connection must not leak.
            connection.close()
            raise
        return connection

    def open_reader(self, path: Path) -> sqlite3.Connection:
        """Opens ``path`` read-only, ``mode=ro`` and ``query_only``, its rows read by column name,
        its temporary b-trees on disk (``temp_store=FILE``): an in-memory sort is unbounded.
        Only the thread that opens it may use or close it."""
        # Not as_uri(), which refuses a relative path.
        connection = sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True)
        connection.row_factory = _build_named_row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA temp_store=FILE")
        return connection


def _connect(path: Path) -> sqlite3.Connection:
    """A connection to ``path`` in WAL, its rows read by column name, its pragmas set and the SQL
    functions registered."""
    with wrap_sqlite_errors():
        connection = sqlite3.connect(path, autocommit=True)
    connection.row_factory = _build_named_row
    try:
        with wrap_sqlite_errors():
            _configure(connection)
            register_sql_functions(connection)
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


def _configure(connection: sqlite3.Connection) -> None:
    journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()["journal_mode"]
    if journal_mode != "wal":
        raise PersistenceError(
            f"journal_mode={journal_mode!r}: WAL required (spec §3), file-backed db only"
        )
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA recursive_triggers=ON")


def _pending_migrations(
    connection: sqlite3.Connection, *, scripts: tuple[Migration, ...]
) -> PendingMigrations:
    """The scripts above the database's ``user_version``; a database newer than the code raises
    ``MigrationError``."""
    with wrap_sqlite_errors():
        current_version = int(connection.execute("PRAGMA user_version").fetchone()["user_version"])
    latest = scripts[-1].version if scripts else 0
    if current_version > latest:
        raise MigrationError(
            f"db at version {current_version}, code at version {latest}: "
            "db newer than the code, refusing to start (spec §3)"
        )
    migrations = tuple(migration for migration in scripts if migration.version > current_version)
    return PendingMigrations(current_version=current_version, migrations=migrations)


def _apply_migrations(connection: sqlite3.Connection, *, pending: PendingMigrations) -> None:
    """Applies the pending scripts in order, each stamped once it succeeds; the rules for
    writing one: ``docs/contributing/architecture.md``, "Écrire une migration"."""
    with wrap_sqlite_errors():
        # On disk: an in-memory sort is unbounded (+697 MB for one index at 11.5M rows).
        connection.execute("PRAGMA temp_store=FILE")
        # No finally: a failed migration fails the open, which closes the connection.
        for migration in pending.migrations:
            _logger.info("migration %d: applying", migration.version)
            _run_restoring_pragmas(connection, migration=migration)
        connection.execute("PRAGMA temp_store=DEFAULT")


def _run_restoring_pragmas(connection: sqlite3.Connection, *, migration: Migration) -> None:
    secure_delete = int(connection.execute("PRAGMA secure_delete").fetchone()["secure_delete"])
    cache_size = int(connection.execute("PRAGMA cache_size").fetchone()["cache_size"])
    if migration.transactional:
        _run_in_transaction(connection, migration=migration)
    else:
        _run_outside_transaction(connection, migration=migration)
    connection.execute(f"PRAGMA secure_delete = {_SECURE_DELETE_MODES[secure_delete]}")
    connection.execute(f"PRAGMA cache_size = {cache_size}")


def _run_in_transaction(connection: sqlite3.Connection, *, migration: Migration) -> None:
    # Two concurrent opens: the loser fails cleanly, single writer by doctrine.
    try:
        connection.execute("BEGIN")
        connection.executescript(migration.script)
        if not connection.in_transaction:
            raise MigrationError(
                f"migration {migration.version}: the script closed its migration's transaction "
                "(COMMIT/ROLLBACK forbidden inside a migration script)"
            )
        connection.execute(f"PRAGMA user_version = {migration.version}")
        connection.execute("COMMIT")
    except sqlite3.Error as error:
        with suppress(sqlite3.Error):
            connection.execute("ROLLBACK")
        raise MigrationError(f"migration {migration.version} failed: {error}") from error


def _run_outside_transaction(connection: sqlite3.Connection, *, migration: Migration) -> None:
    # A stop between the script and the stamp replays the script: it must be safe to replay.
    try:
        connection.executescript(migration.script)
        connection.execute(f"PRAGMA user_version = {migration.version}")
    except sqlite3.Error as error:
        raise MigrationError(f"migration {migration.version} failed: {error}") from error
