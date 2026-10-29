"""``SqliteCatalogScanReader``: walks the whole catalog, for the startup re-evaluation."""

import sqlite3
from collections.abc import Iterator

from p2pwatch.adapters.driven.persistence_sqlite import observation_read
from p2pwatch.adapters.driven.persistence_sqlite.errors import wrap_sqlite_errors
from p2pwatch.application.ports.driven.catalog_scan_reader import CatalogScanReader
from p2pwatch.domain.observation import FileObservation

_COUNT_FILES = "SELECT COUNT(*) AS file_count FROM files"


class SqliteCatalogScanReader(CatalogScanReader):
    """SQLite implementation of the catalog's scan."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def read_file_count(self) -> int:
        """Number of catalogued files, the re-evaluation progress total (read)."""
        with wrap_sqlite_errors():
            row = self._connection.execute(_COUNT_FILES).fetchone()
        return int(row["file_count"])

    def iter_latest_observations(self) -> Iterator[FileObservation]:
        """Every seen file's latest observation, streamed (spec re-evaluation §6)."""
        with wrap_sqlite_errors():
            yield from observation_read.iter_latest_observations(self._connection)
