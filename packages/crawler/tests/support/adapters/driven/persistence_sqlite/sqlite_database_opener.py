"""A migrated ``catalog.db`` or ``local.db`` through ``SqliteDatabaseOpener``, for a test that
only needs an open database."""

import sqlite3
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite.migration_scripts import PendingMigrations
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    SqliteDatabaseOpener,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_pre_migration_copier import (
    SqlitePreMigrationCopier,
)
from tests.fakes.adapters.driven.fake_free_bytes import FakeFreeBytes
from tests.fakes.adapters.driven.fake_time import FakeTime

_AMPLE_BYTES = 1 << 62


class _PragmaSettingCopier(SqlitePreMigrationCopier):
    """Sets a pragma where the opener calls its copier: once the connection is configured, before
    the migrations."""

    def __init__(self, pragma: str) -> None:
        super().__init__(FakeTime().wall, FakeFreeBytes(_AMPLE_BYTES).free_bytes)
        self._pragma = pragma

    def ensure_copy(
        self, connection: sqlite3.Connection, path: Path, pending: PendingMigrations
    ) -> None:
        connection.execute(self._pragma)
        super().ensure_copy(connection, path, pending)


def database_opener() -> SqliteDatabaseOpener:
    """An opener whose pre-migration copies are named from a ``FakeTime`` and never short of
    space."""
    return SqliteDatabaseOpener(
        SqlitePreMigrationCopier(FakeTime().wall, FakeFreeBytes(_AMPLE_BYTES).free_bytes)
    )


def database_opener_setting(pragma: str) -> SqliteDatabaseOpener:
    """The same, ``pragma`` run on each connection before its migrations."""
    return SqliteDatabaseOpener(_PragmaSettingCopier(pragma))


def open_catalog(path: Path) -> sqlite3.Connection:
    """Opens/migrates ``catalog.db``."""
    return database_opener().open_catalog(path)


def open_local(path: Path) -> sqlite3.Connection:
    """Opens/migrates ``local.db``."""
    return database_opener().open_local(path)
