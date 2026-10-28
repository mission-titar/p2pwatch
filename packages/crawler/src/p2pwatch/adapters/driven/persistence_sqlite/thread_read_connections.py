"""Centralized read-only connection management (monolith-consolidation spec §7).

This is the READER side of the persistence adapter, sitting beside the writer's
``SqliteDatabaseOpener``. The crawler is the single writer (WAL, migrations, ``foreign_keys``);
the webui is strictly read-only. This module owns every read open policy so there is ONE
place that decides how a reader is opened and reused.

``open_reader`` opens a single connection in ``mode=ro`` (an OS-level read-only handle) and
sets ``PRAGMA query_only=ON``: a DOUBLE guard, a write is impossible even if the SQL says
otherwise. It NEVER sets ``journal_mode=WAL``/``foreign_keys``/migrations: those are the
writer's job (``SqliteDatabaseOpener``); the reader inherits WAL from the single writer, and an
autocommit read holds no persistent read lock, so a long-lived reader does not block the
writer's WAL checkpointing. ``row_factory = sqlite3.Row`` gives the read adapters access by
column name. ``temp_store=FILE``, as the opener sets it to migrate (stage 1, D8): the temp
b-trees the reads materialize (sorts, ``group_concat``) spill to disk, since an in-memory sort is
unbounded.
The ``MEMORY`` hotfix (461b135) answered a tmpfs ``/tmp`` and ``read_only``, gone since 2026-09-16.

A reader keeps sqlite3's same-thread check: only the thread that opened it may use or close it.

``ThreadReadConnections`` reuses one connection per thread, warming the SQLite page cache instead of
paying a cold open per request.
"""

import sqlite3
import threading
from pathlib import Path
from typing import Self


def open_reader(path: Path | str) -> sqlite3.Connection:
    """Open ``path`` read-only: ``mode=ro`` + ``query_only`` (double guard), ``Row`` factory,
    ``temp_store=FILE``. See the module docstring for the full rationale."""
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA temp_store=FILE")
    return connection


class ThreadLocalConnection(threading.local):
    """The calling thread's connection: ``None`` in each thread until that thread sets it."""

    def __init__(self) -> None:
        self.connection: sqlite3.Connection | None = None


class ThreadReadConnections:
    """A reused, thread-affine read-only connection source: each calling thread gets its OWN
    connection, opened on first use and reused thereafter (warm page cache)."""

    def __init__(self, path: Path | str) -> None:
        self._path = path
        self._local = ThreadLocalConnection()

    def connection(self) -> sqlite3.Connection:
        """Return the calling thread's connection, opening it on first use."""
        existing = self._local.connection
        if existing is not None:
            return existing
        connection = open_reader(self._path)
        self._local.connection = connection
        return connection

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        """Closes the calling thread's connection, which only its own thread may close."""
        connection, self._local.connection = self._local.connection, None
        if connection is not None:
            connection.close()
