"""Local 0010 renames the local waiting reason (descriptive names, D5)."""

from pathlib import Path

from p2pwatch.domain.file_key import FileKey, Network
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import open_local_at

_A = FileKey(network=Network.ED2K, native_id="a" * 32)
_B = FileKey(network=Network.ED2K, native_id="b" * 32)


def test_0010_renames_the_local_waiting_reason_only(tmp_path: Path) -> None:
    path = tmp_path / "local.db"
    connection = open_local_at(path, version=9)
    for file, waiting_reason in ((_A, "local"), (_B, "no_source")):
        connection.execute(
            "INSERT INTO downloads (file_id, network, native_id, target_id, state, queued_at,"
            " waiting_reason) VALUES (?, 'ed2k', ?, '062A', 'downloading', '2026-10-13', ?)",
            (file.file_id, file.native_id, waiting_reason),
        )
    connection.close()

    connection = open_local_at(path, version=10)
    try:
        read = rows(
            connection, sql="SELECT native_id, waiting_reason FROM downloads ORDER BY native_id"
        )
    finally:
        connection.close()
    assert read == [
        {"native_id": _A.native_id, "waiting_reason": "local_processing"},
        {"native_id": _B.native_id, "waiting_reason": "no_source"},
    ]
