"""A migrated ``catalog.db`` or ``local.db`` through ``SqliteDatabaseOpener``, for a test that
only needs an open database."""

import sqlite3
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    SqliteDatabaseOpener,
)


def open_catalog(path: Path) -> sqlite3.Connection:
    """Opens/migrates ``catalog.db``."""
    return SqliteDatabaseOpener().open_catalog(path)


def open_local(path: Path) -> sqlite3.Connection:
    """Opens/migrates ``local.db``."""
    return SqliteDatabaseOpener().open_local(path)
