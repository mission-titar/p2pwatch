"""Pytest fixtures: a migrated catalog.db and local.db, and a closer of a test's connections."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog, open_local


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


@pytest.fixture
def close_test_connections(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Close, at teardown, every SQLite connection a test opens.

    ``sqlite3.Connection.__exit__`` only ends the transaction, it does NOT close.
    """
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracking_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)
    yield
    for connection in opened:
        connection.close()
