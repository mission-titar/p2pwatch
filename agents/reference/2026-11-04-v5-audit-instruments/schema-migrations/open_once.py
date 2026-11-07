# Written for main before v5 lot 2 (fe691fbc): lot 2's opener and copier also take ticker, free_bytes, memory_releaser.
"""Opens <dir>/catalog.db then <dir>/local.db with main's opener, logging each step to stderr."""

import logging
import sys
from pathlib import Path
from shutil import disk_usage

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import SqliteDatabaseOpener
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_pre_migration_copier import (
    SqlitePreMigrationCopier,
)
from p2pwatch.adapters.driven.system_wall_clock import SystemWallClock

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(relativeCreated)7.0fms %(message)s")
directory = Path(sys.argv[1])
opener = SqliteDatabaseOpener(
    SqlitePreMigrationCopier(SystemWallClock(), free_bytes=lambda d: disk_usage(d).free)
)
opener.open_catalog(directory / "catalog.db").close()
opener.open_local(directory / "local.db").close()
print("OPENED", flush=True)
