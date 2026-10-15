"""Shared pytest fixtures for the webui: a migrated catalog.db and local.db."""

import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from p2pwatch.adapters.persistence_sqlite.connection import open_catalog, open_local

# ---------------------------------------------------------------------------
# Fixtures pytest
# ---------------------------------------------------------------------------


@pytest.fixture
def catalog_db(tmp_path: Path) -> Path:
    """An empty catalog.db migrated by the crawler's own migrations."""
    path = tmp_path / "catalog.db"
    open_catalog(path).close()
    return path


@pytest.fixture
def local_db(tmp_path: Path) -> Path:
    """An empty local.db migrated by the crawler's own migrations."""
    path = tmp_path / "local.db"
    open_local(path).close()
    return path


@pytest.fixture(autouse=True)
def _close_test_connections(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Close every SQLite connection a test opens on its own thread.

    The suite pervasively uses ``with sqlite3.connect(...) as conn`` (seeds/fixtures) and
    ``CatalogReader(open_reader(db))`` (readers) without closing. ``sqlite3.Connection.__exit__``
    only ends the transaction, it does NOT close, so each connection lingers until GC and
    surfaces as ``ResourceWarning: unclosed database``. This wraps ``sqlite3.connect`` for the
    duration of each test, tracks every connection it hands out on the test's thread
    (``open_reader`` opens through it too), and closes them at teardown. The app's
    ``ReaderProvider`` connections are among them, since the app runs on the test's event loop;
    the provider deliberately REUSES them across requests (never closing per request), so this
    teardown is what closes them when the test app is discarded. A connection opened on another
    thread is that thread's to close (``run_query`` closes its own): sqlite3 refuses any other.
    """
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect
    test_thread_id = threading.get_ident()

    def tracking_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = real_connect(*args, **kwargs)
        if threading.get_ident() == test_thread_id:
            opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)
    yield
    for connection in opened:
        connection.close()
