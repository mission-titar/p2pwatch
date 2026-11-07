"""Probe: time database_digest on a database opened read-only, as the copier does.

probe_digest.py DB
"""

import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite.database_digest import database_digest
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    SqliteDatabaseOpener,
)

opener = SqliteDatabaseOpener.__new__(SqliteDatabaseOpener)
start = time.monotonic()
with closing(opener.open_reader(Path(sys.argv[1]))) as connection:
    digest = database_digest(connection)
print(f"digest {digest.hex()[:12]} in {time.monotonic() - start:.1f} s", flush=True)
