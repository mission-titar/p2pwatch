"""Reuses one read-only connection per thread (monolith-consolidation spec §7), warming the SQLite
page cache instead of paying a cold open per request.

The webui is strictly read-only: each connection comes from the ``open_reader`` it is given,
``SqliteDatabaseOpener.open_reader``. An autocommit read holds no persistent read lock, so a
long-lived reader does not block the writer's WAL checkpointing.
"""

import sqlite3
import threading
from pathlib import Path
from typing import Self

from p2pwatch.adapters.driven.persistence_sqlite.reader_opener import ReaderOpener


class ThreadLocalConnection(threading.local):
    """The calling thread's connection: ``None`` in each thread until that thread sets it."""

    def __init__(self) -> None:
        self.connection: sqlite3.Connection | None = None


class ThreadReadConnections:
    """A reused, thread-affine read-only connection source: each calling thread gets its OWN
    connection to ``path``, opened by ``open_reader`` on first use and reused thereafter."""

    def __init__(self, path: Path, open_reader: ReaderOpener) -> None:
        self._path = path
        self._open_reader = open_reader
        self._local = ThreadLocalConnection()

    def connection(self) -> sqlite3.Connection:
        """Return the calling thread's connection, opening it on first use."""
        existing = self._local.connection
        if existing is not None:
            return existing
        connection = self._open_reader(self._path)
        self._local.connection = connection
        return connection

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        """Closes the calling thread's connection, which only its own thread may close."""
        connection, self._local.connection = self._local.connection, None
        if connection is not None:
            connection.close()
