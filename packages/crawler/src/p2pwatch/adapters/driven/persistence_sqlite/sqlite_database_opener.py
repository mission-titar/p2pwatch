"""Opens ``catalog.db`` and ``local.db``, each migrated to the code's version."""

import sqlite3
from importlib import resources
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite.connection import (
    Migration,
    apply_migrations,
    connect,
    load_scripts,
    pending_migrations,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_pre_migration_copier import (
    SqlitePreMigrationCopier,
)

_MIGRATIONS = resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations"


class SqliteDatabaseOpener:
    """Opens a database and applies its pending migrations, the one way the code opens one."""

    def __init__(self, pre_migration_copier: SqlitePreMigrationCopier) -> None:
        self._pre_migration_copier = pre_migration_copier

    def open_catalog(self, path: Path) -> sqlite3.Connection:
        """Opens/migrates ``catalog.db`` (the append-only triggers are part of the schema)."""
        return self._open(path, load_scripts(_MIGRATIONS / "catalog"))

    def open_local(self, path: Path) -> sqlite3.Connection:
        """Opens/migrates ``local.db``."""
        return self._open(path, load_scripts(_MIGRATIONS / "local"))

    def _open(self, path: Path, scripts: tuple[Migration, ...]) -> sqlite3.Connection:
        connection = connect(path)
        try:
            pending = pending_migrations(connection, scripts)
            self._pre_migration_copier.ensure_copy(connection, path, pending)
            apply_migrations(connection, pending)
        except BaseException:
            # Unconditional close: whatever fails, the connection must not leak.
            connection.close()
            raise
        return connection
