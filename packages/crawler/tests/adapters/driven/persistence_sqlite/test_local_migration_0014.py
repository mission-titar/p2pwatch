"""Local 0014 rebuilds ``downloads`` STRICT, its four stamps as micros (micros spec)."""

import sqlite3
from pathlib import Path

import pytest

from p2pwatch.domain.file_key import FileKey, Network
from tests.support.adapters.driven.persistence_sqlite.older_catalog import open_local_at

_A = FileKey(Network.ED2K, "a" * 32)
_B = FileKey(Network.ED2K, "b" * 32)
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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 14
        assert connection.execute(
            "SELECT file_id, network, native_id, target_id, state, queued_at_micros,"
            " completed_at_micros, size_bytes, latest_seen_at_micros, bytes_done,"
            " latest_progress_at_micros, waiting_reason, failure_reason"
            " FROM downloads ORDER BY native_id"
        ).fetchall() == [
            (
                _A.file_id,
                "ed2k",
                _A.native_id,
                "062A",
                "completed",
                1_781_179_200_123_456,
                1_781_265_600_000_000,
                100,
                1_781_182_800_000_001,
                40,
                1_781_173_800_000_000,
                None,
                "error",
            ),
            (_B.file_id, "ed2k", _B.native_id, "062A", "queued", 1_781_179_200_000_000)
            + (None, 100, None, None, None, None, None),
        ]
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        connection.close()


def test_0014_rebuilds_downloads_strict_with_its_stamps_typed(tmp_path: Path) -> None:
    connection = _migrated(tmp_path)
    try:
        assert connection.execute(
            "SELECT strict FROM pragma_table_list WHERE name = 'downloads'"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT name, type, \"notnull\" FROM pragma_table_info('downloads')"
            " WHERE name GLOB '*_at*' ORDER BY cid"
        ).fetchall() == [
            ("queued_at_micros", "INTEGER", 1),
            ("completed_at_micros", "INTEGER", 0),
            ("latest_seen_at_micros", "INTEGER", 0),
            ("latest_progress_at_micros", "INTEGER", 0),
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
