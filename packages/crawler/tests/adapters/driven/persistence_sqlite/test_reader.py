"""Tests for the read-only connection provider (monolith-consolidation spec §7).

Folds the assertions of the deleted webui ``test_webui_db.py`` (RO-refuses-writes,
``temp_store``, ``row_factory`` dict access, reads rows) plus the provider's
per-thread reuse and thread affinity.
"""

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog
from p2pwatch.adapters.driven.persistence_sqlite.reader import (
    ReaderProvider,
    ThreadLocalConnection,
    open_reader,
)
from p2pwatch_testing.catalog_rows import insert_file

_HASH_A = "a" * 32
_HASH_B = "b" * 32


def _seed(path: Path) -> None:
    """Create + seed a real catalog.db via the writer (readers need a real file, mode=ro)."""
    writer = open_catalog(path)
    try:
        insert_file(writer, _HASH_A, 10)
    finally:
        writer.close()


# ---------------------------------------------------------------------------
# open_reader (low-level single connection)
# ---------------------------------------------------------------------------


def test_open_reader_reads_seeded_row_with_dict_access(tmp_path: Path) -> None:
    """A seeded row is readable and ``row_factory`` gives dict access (``row["col"]``)."""
    path = tmp_path / "catalog.db"
    _seed(path)
    reader = open_reader(path)
    try:
        row = reader.execute("SELECT native_id, size_bytes FROM files").fetchone()
        assert row["native_id"] == _HASH_A
        assert row["size_bytes"] == 10
    finally:
        reader.close()


def test_open_reader_refuses_writes(tmp_path: Path) -> None:
    """``mode=ro`` + ``query_only`` is a double guard: an INSERT raises ``OperationalError``."""
    path = tmp_path / "catalog.db"
    _seed(path)
    reader = open_reader(path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            insert_file(reader, _HASH_B, 1)
    finally:
        reader.close()


def test_open_reader_sorts_through_temporary_files(tmp_path: Path) -> None:
    """``temp_store=FILE`` (1), as the runner's: an in-memory sort is unbounded (stage 1, D8)."""
    path = tmp_path / "catalog.db"
    _seed(path)
    reader = open_reader(path)
    try:
        assert reader.execute("PRAGMA temp_store").fetchone()[0] == 1  # 1 == FILE
    finally:
        reader.close()


def test_open_reader_refuses_use_from_another_thread(tmp_path: Path) -> None:
    """A reader belongs to the thread that opened it: a query from another thread raises."""
    path = tmp_path / "catalog.db"
    _seed(path)
    reader = open_reader(path)
    with ThreadPoolExecutor(max_workers=1) as executor:
        query = executor.submit(reader.execute, "SELECT 1")
    try:
        with pytest.raises(sqlite3.ProgrammingError, match="same thread"):
            query.result()
    finally:
        reader.close()


# ---------------------------------------------------------------------------
# ReaderProvider (reused per-thread connection)
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


def test_provider_reuses_the_same_connection_within_one_thread(tmp_path: Path) -> None:
    """Repeated ``connection()`` calls from one thread return the SAME object (warm cache)."""
    path = tmp_path / "catalog.db"
    _seed(path)
    provider = ReaderProvider(path)
    first = provider.connection()
    try:
        assert provider.connection() is first
    finally:
        first.close()


def test_provider_gives_a_distinct_connection_per_thread(tmp_path: Path) -> None:
    """Two different threads each get their OWN connection (thread affinity)."""
    path = tmp_path / "catalog.db"
    _seed(path)
    provider = ReaderProvider(path)
    connections: dict[str, sqlite3.Connection] = {}

    def worker(name: str) -> None:
        connection = provider.connection()
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
    provider = ReaderProvider(path)
    writer = open_catalog(path)
    reader = provider.connection()
    try:
        assert reader.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1
        insert_file(writer, _HASH_B, 20)
        reused = provider.connection()
        assert reused is reader
        assert reused.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 2
    finally:
        writer.close()
        reader.close()


def test_leaving_the_provider_closes_the_calling_threads_connection(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    _seed(path)
    with ReaderProvider(path) as provider:
        first = provider.connection()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        first.execute("SELECT 1")
    reopened = provider.connection()  # a later read opens a fresh one
    try:
        assert reopened is not first
    finally:
        reopened.close()


def test_leaving_the_provider_unused_opens_nothing(tmp_path: Path) -> None:
    with ReaderProvider(tmp_path / "never-opened.db"):
        pass
    assert not (tmp_path / "never-opened.db").exists()
