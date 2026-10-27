"""A migrated ``catalog.db`` or ``local.db`` through ``SqliteDatabaseOpener``, for a test that
only needs an open database."""

import sqlite3
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    SqliteDatabaseOpener,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_pre_migration_copier import (
    SqlitePreMigrationCopier,
)
from tests.fakes.adapters.driven.fake_free_bytes import FakeFreeBytes
from tests.fakes.adapters.driven.fake_time import FakeTime

_AMPLE_BYTES = 1 << 62


def database_opener() -> SqliteDatabaseOpener:
    """An opener whose pre-migration copies are named from a ``FakeTime`` and never short of
    space."""
    return SqliteDatabaseOpener(
        SqlitePreMigrationCopier(FakeTime().wall, FakeFreeBytes(_AMPLE_BYTES).free_bytes)
    )


def open_catalog(path: Path) -> sqlite3.Connection:
    """Opens/migrates ``catalog.db``."""
    return database_opener().open_catalog(path)


def open_local(path: Path) -> sqlite3.Connection:
    """Opens/migrates ``local.db``."""
    return database_opener().open_local(path)
