"""The crawler as the image runs it, with malloc_trim(0) after each database open: the candidate fix.

python crawl_with_trim.py <the crawl command line's arguments>
"""

import ctypes
import logging
import os
import sys
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite import sqlite_database_opener
from p2pwatch.composition.command_line import build_command_line

_trim = ctypes.CDLL("libc.so.6").malloc_trim
_open = sqlite_database_opener.SqliteDatabaseOpener.open


def open_then_trim(self, path, *, scripts):
    connection = _open(self, path, scripts=scripts)
    _trim(0)
    return connection


sqlite_database_opener.SqliteDatabaseOpener.open = open_then_trim
command_line = build_command_line(env=os.environ, cwd=Path.cwd(), root_logger=logging.getLogger())
raise SystemExit(command_line.run(sys.argv[1:]))
