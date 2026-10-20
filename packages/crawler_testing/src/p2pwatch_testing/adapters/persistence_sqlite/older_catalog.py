import hashlib
import sqlite3
from collections.abc import Callable
from importlib import resources
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite import connection as connection_module
from p2pwatch.adapters.driven.persistence_sqlite.variants import (
    content_hash,
    register_sql_functions,
)
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.source import SourceKey

_MIGRATIONS = resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations"


def open_catalog_at(
    path: Path,
    version: int,
    *,
    configure: Callable[[sqlite3.Connection], None] = connection_module._configure,
) -> sqlite3.Connection:
    """A catalog.db migrated by the runner up to ``version`` only, as an older release left it."""
    return _open_at(path, "catalog", version, configure)


def open_local_at(path: Path, version: int) -> sqlite3.Connection:
    """The same for a local.db."""
    return _open_at(path, "local", version, connection_module._configure)


def _open_at(
    path: Path,
    database: str,
    version: int,
    configure: Callable[[sqlite3.Connection], None],
) -> sqlite3.Connection:
    connection = sqlite3.connect(path, autocommit=True)
    configure(connection)
    register_sql_functions(connection)
    scripts = connection_module._load_scripts(_MIGRATIONS / database)
    connection_module._apply_migrations(
        connection, tuple(s for s in scripts if s.version <= version)
    )
    return connection


def configure_forcing_secure_delete(connection: sqlite3.Connection) -> None:
    """Configures as the runner does, then stands for the image's SQLite, which compiles
    ``SECURE_DELETE`` in."""
    connection_module._configure(connection)
    connection.execute("PRAGMA secure_delete = ON")


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


def insert_v11_observation(
    conn: sqlite3.Connection,
    ed2k_hash: str,
    filename: str,
    *,
    observed_at: int = 10,
    media_length_sec: int | None = None,
) -> None:
    """An observation of versions 8 to 11, before 0012 renamed ``media_length_sec``."""
    variant = (FileKey(Network.ED2K, ed2k_hash).file_id, filename, 100, media_length_sec)
    key = content_hash(*variant, None, "[]", "keroro", "n1")
    conn.execute(
        "INSERT INTO observation_variants (file_id, filename, size_bytes, media_length_sec,"
        " raw_meta, keyword, node_id, content_hash) VALUES (?, ?, ?, ?, '[]', 'keroro', 'n1', ?)",
        (*variant, key),
    )
    conn.execute(
        "INSERT INTO observations (variant_id, observed_at, source_count)"
        " SELECT variant_id, ?, 1 FROM observation_variants WHERE content_hash = ?",
        (observed_at, key),
    )


def insert_v11_source_point(
    conn: sqlite3.Connection,
    ed2k_hash: str,
    user_hash: str,
    *,
    directly_reachable: bool,
    transfer_counter: int,
) -> None:
    """A ``source_variants`` row of version 11 and one point of it, before 0012's renames."""
    key = hashlib.blake2b(repr((ed2k_hash, user_hash)).encode(), digest_size=16).digest()
    row = conn.execute(
        "INSERT INTO source_variants (file_id, source_id, name, role, directly_reachable,"
        " raw_meta, node_id, content_hash)"
        " VALUES (?, ?, 'AnimuseeFMR', 'sending', ?, '{}', 'n1', ?) RETURNING variant_id",
        (
            FileKey(Network.ED2K, ed2k_hash).file_id,
            SourceKey(Network.ED2K, user_hash).source_id,
            directly_reachable,
            key,
        ),
    ).fetchone()
    conn.execute(
        "INSERT INTO source_observations (variant_id, observed_at, transfer_counter)"
        " VALUES (?, 20, ?)",
        (row[0], transfer_counter),
    )
