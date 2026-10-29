"""What opens a read-only connection to a database: ``SqliteDatabaseOpener.open_reader``."""

import sqlite3
from pathlib import Path
from typing import Protocol


class ReaderOpener(Protocol):
    def __call__(self, path: Path, /) -> sqlite3.Connection: ...
