"""Local 0010 renames the backoff key and the local waiting reason (descriptive names, D5)."""

from pathlib import Path

from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch_testing.adapters.persistence_sqlite.older_catalog import open_local_at

_A = FileKey(Network.ED2K, "a" * 32)
_B = FileKey(Network.ED2K, "b" * 32)
_BACKOFF_ROW = '{"amuled:kad": {"attempts": 2, "retry_after": "2026-10-13T00:03:00.000000+00:00"}}'


def test_0010_renames_the_backoff_key_and_keeps_its_states(tmp_path: Path) -> None:
    path = tmp_path / "local.db"
    connection = open_local_at(path, 9)
    connection.execute(
        "INSERT INTO scheduler_state (key, value) VALUES ('channel_backoff', ?)", (_BACKOFF_ROW,)
    )
    connection.close()

    connection = open_local_at(path, 10)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 10
        assert connection.execute("SELECT key, value FROM scheduler_state").fetchall() == [
            ("backoff_states", _BACKOFF_ROW)
        ]
    finally:
        connection.close()


def test_0010_renames_the_local_waiting_reason_only(tmp_path: Path) -> None:
    path = tmp_path / "local.db"
    connection = open_local_at(path, 9)
    for file, waiting_reason in ((_A, "local"), (_B, "no_source")):
        connection.execute(
            "INSERT INTO downloads (file_id, network, native_id, target_id, state, queued_at,"
            " waiting_reason) VALUES (?, 'ed2k', ?, '062A', 'downloading', '2026-10-13', ?)",
            (file.file_id, file.native_id, waiting_reason),
        )
    connection.close()

    connection = open_local_at(path, 10)
    try:
        rows = connection.execute(
            "SELECT native_id, waiting_reason FROM downloads ORDER BY native_id"
        ).fetchall()
    finally:
        connection.close()
    assert rows == [(_A.native_id, "local_processing"), (_B.native_id, "no_source")]
