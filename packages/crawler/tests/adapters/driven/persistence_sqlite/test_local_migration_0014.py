"""Local 0014 rebuilds ``downloads`` STRICT, its four stamps as micros (micros spec)."""

import sqlite3
from pathlib import Path

import pytest

from p2pwatch.domain.file_key import FileKey, Network
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import open_local_at

_A = FileKey(network=Network.ED2K, native_id="a" * 32)
_B = FileKey(network=Network.ED2K, native_id="b" * 32)
_INSERT_V13_DOWNLOAD = (
    "INSERT INTO downloads (file_id, network, native_id, target_id, state, queued_at,"
    " completed_at, size_bytes, latest_seen_at, bytes_done, latest_progress_at, waiting_reason,"
    " failure_reason) VALUES (?, 'ed2k', ?, '062A', ?, ?, ?, 100, ?, ?, ?, ?, ?)"
)


def _migrated(tmp_path: Path) -> sqlite3.Connection:
    """A local.db at 14 from one at 13 holding a completed download and a fresh one."""
    path = tmp_path / "local.db"
    connection = open_local_at(path, 13)
    connection.execute(
        _INSERT_V13_DOWNLOAD,
        (
            _A.file_id,
            _A.native_id,
            "completed",
            "2026-06-11T12:00:00.123456+00:00",
            "2026-06-12T12:00:00+00:00",
            "2026-06-11T13:00:00.000001+00:00",
            40,
            "2026-06-11T12:30:00+02:00",
            None,
            "error",
        ),
    )
    connection.execute(
        _INSERT_V13_DOWNLOAD,
        (_B.file_id, _B.native_id, "queued", "2026-06-11T12:00:00+00:00", *[None] * 6),
    )
    connection.close()
    return open_local_at(path, 14)


def test_0014_converts_each_download_stamp_to_micros_and_keeps_a_null(tmp_path: Path) -> None:
    connection = _migrated(tmp_path)
    try:
        assert rows(connection, "PRAGMA user_version") == [{"user_version": 14}]
        completed = {
            "file_id": _A.file_id,
            "network": "ed2k",
            "native_id": _A.native_id,
            "target_id": "062A",
            "state": "completed",
            "queued_at_micros": 1_781_179_200_123_456,
            "completed_at_micros": 1_781_265_600_000_000,
            "size_bytes": 100,
            "latest_seen_at_micros": 1_781_182_800_000_001,
            "bytes_done": 40,
            "latest_progress_at_micros": 1_781_173_800_000_000,
            "waiting_reason": None,
            "failure_reason": "error",
        }
        queued = completed | {
            "file_id": _B.file_id,
            "native_id": _B.native_id,
            "state": "queued",
            "queued_at_micros": 1_781_179_200_000_000,
            "completed_at_micros": None,
            "latest_seen_at_micros": None,
            "bytes_done": None,
            "latest_progress_at_micros": None,
            "failure_reason": None,
        }
        assert rows(connection, "SELECT * FROM downloads ORDER BY native_id") == [
            completed,
            queued,
        ]
        assert rows(connection, "PRAGMA integrity_check") == [{"integrity_check": "ok"}]
    finally:
        connection.close()


def test_0014_rebuilds_downloads_strict_with_its_stamps_typed(tmp_path: Path) -> None:
    connection = _migrated(tmp_path)
    try:
        assert rows(
            connection, "SELECT strict FROM pragma_table_list WHERE name = 'downloads'"
        ) == [{"strict": 1}]
        assert rows(
            connection,
            "SELECT name, type, \"notnull\" FROM pragma_table_info('downloads')"
            " WHERE name GLOB '*_at*' ORDER BY cid",
        ) == [
            {"name": "queued_at_micros", "type": "INTEGER", "notnull": 1},
            {"name": "completed_at_micros", "type": "INTEGER", "notnull": 0},
            {"name": "latest_seen_at_micros", "type": "INTEGER", "notnull": 0},
            {"name": "latest_progress_at_micros", "type": "INTEGER", "notnull": 0},
        ]
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            connection.execute(
                "INSERT INTO downloads (file_id, network, native_id, target_id, state,"
                " queued_at_micros) VALUES (x'00', 'ed2k', ?, '062A', 'queued', 0)",
                (_A.native_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="cannot store TEXT value"):
            connection.execute(
                "UPDATE downloads SET completed_at_micros = '2026-06-12T12:00:00+00:00'"
            )
    finally:
        connection.close()
