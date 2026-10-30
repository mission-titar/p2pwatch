"""Local 0008 adds the downloads' lifecycle columns (stage 2, D12, D19)."""

from pathlib import Path

from p2pwatch.domain.file_key import FileKey, Network
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import open_local_at

_A = FileKey(network=Network.ED2K, native_id="a" * 32)


def test_0008_adds_the_lifecycle_columns_unknown_on_existing_rows(tmp_path: Path) -> None:
    path = tmp_path / "local.db"
    connection = open_local_at(path, version=7)
    connection.execute(
        "INSERT INTO downloads (file_id, network, native_id, target_id, state, queued_at)"
        " VALUES (?, 'ed2k', ?, '062A', 'downloading', '2026-10-01')",
        (_A.file_id, _A.native_id),
    )
    connection.close()

    connection = open_local_at(path, version=8)
    try:
        assert rows(connection, sql="PRAGMA user_version") == [{"user_version": 8}]
        read = rows(
            connection,
            sql="SELECT native_id, state, bytes_done, last_progress_at, waiting_reason,"
            " failure_reason FROM downloads",
        )
    finally:
        connection.close()
    # bytes_done NULL: what the client held before 0008 is unknown, so no progress is invented.
    assert read == [
        {
            "native_id": _A.native_id,
            "state": "downloading",
            "bytes_done": None,
            "last_progress_at": None,
            "waiting_reason": None,
            "failure_reason": None,
        }
    ]
