import hashlib
import sqlite3
from importlib import resources
from pathlib import Path

import pytest

from p2pwatch.adapters.persistence_sqlite import connection as connection_module
from p2pwatch.adapters.persistence_sqlite.variants import register_functions
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.source import SourceKey

_MIGRATIONS = resources.files("p2pwatch.adapters.persistence_sqlite") / "migrations"


def open_catalog_at(path: Path, version: int) -> sqlite3.Connection:
    """A catalog.db migrated by the runner up to ``version`` only, as an older release left it."""
    return _open_at(path, "catalog", version)


def open_local_at(path: Path, version: int) -> sqlite3.Connection:
    """The same for a local.db."""
    return _open_at(path, "local", version)


def _open_at(path: Path, database: str, version: int) -> sqlite3.Connection:
    connection = sqlite3.connect(path, autocommit=True)
    connection_module._configure(connection)
    register_functions(connection)
    scripts = connection_module._load_scripts(_MIGRATIONS / database)
    connection_module._apply_migrations(
        connection, tuple(s for s in scripts if s.version <= version)
    )
    return connection


def forcing_secure_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stands for the image's SQLite, which compiles ``SECURE_DELETE`` in."""
    configure = connection_module._configure

    def configure_then_force(connection: sqlite3.Connection) -> None:
        configure(connection)
        connection.execute("PRAGMA secure_delete = ON")

    monkeypatch.setattr(connection_module, "_configure", configure_then_force)


def insert_stage4_variant(
    conn: sqlite3.Connection,
    ed2k_hash: str,
    user_hash: str | None,
    *,
    name: str | None = "AnimuseeFMR",
    role: str = "queued",
) -> int:
    """A ``source_variants`` row of version 10, which has no ``node_id``; its ``variant_id``."""
    sid = None if user_hash is None else SourceKey(Network.ED2K, user_hash).source_id
    key = hashlib.blake2b(repr((ed2k_hash, user_hash, name, role)).encode(), digest_size=16)
    row = conn.execute(
        "INSERT INTO source_variants (file_id, source_id, name, role, raw_meta, content_hash)"
        " VALUES (?, ?, ?, ?, '{}', ?) RETURNING variant_id",
        (FileKey(Network.ED2K, ed2k_hash).file_id, sid, name, role, key.digest()),
    ).fetchone()
    variant_id: int = row[0]
    return variant_id


def insert_stage4_range(
    conn: sqlite3.Connection,
    variant_id: int,
    first_seen_at: int,
    last_seen_at: int,
    *,
    node_id: str = "n1",
    received_bytes: int = 0,
    transfer_counter: int = 0,
) -> None:
    """A ``source_ranges`` row of version 10."""
    conn.execute(
        "INSERT INTO source_ranges (variant_id, node_id, first_seen_at, last_seen_at,"
        " received_bytes, transfer_counter) VALUES (?, ?, ?, ?, ?, ?)",
        (variant_id, node_id, first_seen_at, last_seen_at, received_bytes, transfer_counter),
    )
