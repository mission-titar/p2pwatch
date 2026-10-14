"""Local 0009 renames the re-evaluation marker's table and column (descriptive names, D5)."""

from pathlib import Path

from p2pwatch.adapters.persistence_sqlite.local_state_repository import SqliteLocalStateRepository
from tests.adapters.persistence_sqlite.older_catalog import open_local_at


def test_0009_renames_the_marker_and_keeps_its_fingerprint(tmp_path: Path) -> None:
    path = tmp_path / "local.db"
    connection = open_local_at(path, 8)
    connection.execute("INSERT INTO backfill_state (id, policy_sha256) VALUES (1, 'abc')")
    connection.close()

    connection = open_local_at(path, 9)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 9
        repository = SqliteLocalStateRepository(connection)
        assert repository.reevaluated_policy_fingerprint() == "abc"
    finally:
        connection.close()
