"""Local 0009 renames the re-evaluation marker's table and column (descriptive names, D5)."""

from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_policy_fingerprint_store import (
    SqlitePolicyFingerprintStore,
)
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import open_local_at


def test_0009_renames_the_marker_and_keeps_its_fingerprint(tmp_path: Path) -> None:
    path = tmp_path / "local.db"
    connection = open_local_at(path, version=8)
    connection.execute("INSERT INTO backfill_state (id, policy_sha256) VALUES (1, 'abc')")
    connection.close()

    connection = open_local_at(path, version=9)
    try:
        assert rows(connection, sql="PRAGMA user_version") == [{"user_version": 9}]
        policy_fingerprint_store = SqlitePolicyFingerprintStore(connection)
        assert policy_fingerprint_store.read_policy_fingerprint() == "abc"
    finally:
        connection.close()
