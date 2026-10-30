"""Local 0007 keys downloads by ``file_id`` and keeps ``(network, native_id)`` (stage 2, D19)."""

import sqlite3
from pathlib import Path

import pytest

from p2pwatch.domain.file_key import FileKey, Network
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import open_local_at
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_local

_A, _B = "a" * 32, "0123456789abcdef" * 2
_ROWS = (
    (_A, "062A", "downloading", "2026-10-01T00:00:00.000000+00:00", None, 100, "2026-10-09"),
    (_B, "063B", "completed", "2026-10-02T00:00:00.000000+00:00", "2026-10-03", 200, None),
)
_KEPT_COLUMNS = (
    "native_id",
    "target_id",
    "state",
    "queued_at",
    "completed_at",
    "size_bytes",
    "last_seen_at",
)


def _write_local_db_at_version_6(path: Path) -> None:
    connection = open_local_at(path, 6)
    connection.executemany(
        "INSERT INTO downloads (ed2k_hash, target_id, state, queued_at, completed_at,"
        " size_bytes, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        _ROWS,
    )
    connection.close()


def test_0007_keys_each_download_by_the_catalog_file_id(tmp_path: Path) -> None:
    path = tmp_path / "local.db"
    _write_local_db_at_version_6(path)

    connection = open_local_at(path, 7)
    try:
        assert rows(connection, "PRAGMA user_version") == [{"user_version": 7}]
        read = rows(connection, "SELECT * FROM downloads ORDER BY native_id")
    finally:
        connection.close()
    assert read == [
        {"file_id": FileKey(network=Network.ED2K, native_id=native_id).file_id, "network": "ed2k"}
        | dict(zip(_KEPT_COLUMNS, (native_id, *kept), strict=True))
        for native_id, *kept in sorted(_ROWS)
    ]


@pytest.mark.parametrize(
    ("network", "native_id"),
    [("gnutella", _A), ("ed2k", "A" * 32), ("ed2k", "a" * 31)],
)
def test_0007_refuses_a_native_id_its_network_does_not_define(
    tmp_path: Path, network: str, native_id: str
) -> None:
    connection = open_local(tmp_path / "local.db")
    try:
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            connection.execute(
                "INSERT INTO downloads"
                " (file_id, network, native_id, target_id, state, queued_at_micros)"
                " VALUES (x'00', ?, ?, '062A', 'queued', 0)",
                (network, native_id),
            )
    finally:
        connection.close()
