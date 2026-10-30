"""Tests for ``ThreadReadConnections`` (monolith-consolidation spec §7): per-thread reuse and
thread affinity."""

import sqlite3
import threading
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import (
    ThreadLocalConnection,
    ThreadReadConnections,
)
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    open_catalog,
    open_reader,
)
from tests.support.catalog_rows import insert_file

_HASH_A = "a" * 32
_HASH_B = "b" * 32
_FILE_COUNT = "SELECT COUNT(*) AS file_count FROM files"


def _seed(path: Path) -> None:
    """Create + seed a real catalog.db via the writer (readers need a real file, mode=ro)."""
    writer = open_catalog(path)
    try:
        insert_file(writer, native_id=_HASH_A, size_bytes=10)
    finally:
        writer.close()


# ---------------------------------------------------------------------------
# ThreadReadConnections (reused per-thread connection)
# ---------------------------------------------------------------------------


def test_thread_local_connection_is_none_in_a_thread_that_never_set_it() -> None:
    """A connection set by one thread is never seen by another, which starts from ``None``."""
    local = ThreadLocalConnection()
    connection = sqlite3.connect(":memory:")
    local.connection = connection
    seen_by_worker: list[sqlite3.Connection | None] = []
    worker = threading.Thread(target=lambda: seen_by_worker.append(local.connection))
    worker.start()
    worker.join()
    try:
        assert seen_by_worker == [None]
        assert local.connection is connection
    finally:
        connection.close()


def test_a_connection_is_opened_by_the_open_reader_it_is_given(tmp_path: Path) -> None:
    opened: list[Path] = []

    def open_in_memory(path: Path) -> sqlite3.Connection:
        opened.append(path)
        return sqlite3.connect(":memory:")

    with ThreadReadConnections(
        tmp_path / "catalog.db", open_reader=open_in_memory
    ) as thread_read_connections:
        thread_read_connections.connection()
    assert opened == [tmp_path / "catalog.db"]


def test_the_same_connection_is_reused_within_one_thread(tmp_path: Path) -> None:
    """Repeated ``connection()`` calls from one thread return the SAME object (warm cache)."""
    path = tmp_path / "catalog.db"
    _seed(path)
    thread_read_connections = ThreadReadConnections(path, open_reader=open_reader)
    first = thread_read_connections.connection()
    try:
        assert thread_read_connections.connection() is first
    finally:
        first.close()


def test_each_thread_gets_a_distinct_connection(tmp_path: Path) -> None:
    """Two different threads each get their OWN connection (thread affinity)."""
    path = tmp_path / "catalog.db"
    _seed(path)
    thread_read_connections = ThreadReadConnections(path, open_reader=open_reader)
    connections: dict[str, sqlite3.Connection] = {}

    def worker(name: str) -> None:
        connection = thread_read_connections.connection()
        connections[name] = connection
        connection.close()  # only its own thread may close it

    first = threading.Thread(target=worker, args=("first",))
    second = threading.Thread(target=worker, args=("second",))
    first.start()
    second.start()
    first.join()
    second.join()
    assert id(connections["first"]) != id(connections["second"])
    assert connections["first"] is not connections["second"]


def test_reused_connection_sees_data_committed_after_first_handout(tmp_path: Path) -> None:
    """A reused reader sees state committed AFTER it was first handed out: autocommit reads
    see the current committed snapshot, proving reuse is correct, not a stale snapshot."""
    path = tmp_path / "catalog.db"
    _seed(path)  # one row so far
    thread_read_connections = ThreadReadConnections(path, open_reader=open_reader)
    writer = open_catalog(path)
    reader = thread_read_connections.connection()
    try:
        assert rows(reader, sql=_FILE_COUNT) == [{"file_count": 1}]
        insert_file(writer, native_id=_HASH_B, size_bytes=20)
        reused = thread_read_connections.connection()
        assert reused is reader
        assert rows(reused, sql=_FILE_COUNT) == [{"file_count": 2}]
    finally:
        writer.close()
        reader.close()


def test_leaving_the_context_closes_the_calling_threads_connection(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    _seed(path)
    with ThreadReadConnections(path, open_reader=open_reader) as thread_read_connections:
        first = thread_read_connections.connection()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        first.execute("SELECT 1")
    reopened = thread_read_connections.connection()  # a later read opens a fresh one
    try:
        assert reopened is not first
    finally:
        reopened.close()


def test_leaving_the_context_unused_opens_nothing(tmp_path: Path) -> None:
    with ThreadReadConnections(tmp_path / "never-opened.db", open_reader=open_reader):
        pass
    assert not (tmp_path / "never-opened.db").exists()
