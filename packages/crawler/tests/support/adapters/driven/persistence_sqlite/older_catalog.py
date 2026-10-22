import hashlib
import sqlite3
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


def open_catalog_at(path: Path, version: int) -> sqlite3.Connection:
    """A catalog.db migrated by the runner up to ``version`` only, as an older release left it."""
    return connection_module._open(path, _scripts_up_to("catalog", version))


def open_catalog_forcing_secure_delete_at(path: Path, version: int) -> sqlite3.Connection:
    """The same, ``secure_delete`` ON: stands for the image's SQLite, which compiles it in."""
    connection = sqlite3.connect(path, autocommit=True)
    try:
        connection_module._configure(connection)
        connection.execute("PRAGMA secure_delete = ON")
        register_sql_functions(connection)
        connection_module._apply_migrations(connection, _scripts_up_to("catalog", version))
    except BaseException:
        connection.close()
        raise
    return connection


def open_local_at(path: Path, version: int) -> sqlite3.Connection:
    """The same for a local.db."""
    return connection_module._open(path, _scripts_up_to("local", version))


def _scripts_up_to(database: str, version: int) -> tuple[connection_module.Migration, ...]:
    scripts = connection_module._load_scripts(_MIGRATIONS / database)
    return tuple(script for script in scripts if script.version <= version)


def insert_stage4_variant(
    connection: sqlite3.Connection,
    ed2k_hash: str,
    user_hash: str | None,
    *,
    name: str | None = "AnimuseeFMR",
    role: str = "queued",
) -> int:
    """A ``source_variants`` row of version 10, which has no ``node_id``; its ``variant_id``."""
    sid = None if user_hash is None else SourceKey(Network.ED2K, user_hash).source_id
    key = hashlib.blake2b(repr((ed2k_hash, user_hash, name, role)).encode(), digest_size=16)
    row = connection.execute(
        "INSERT INTO source_variants (file_id, source_id, name, role, raw_meta, content_hash)"
        " VALUES (?, ?, ?, ?, '{}', ?) RETURNING variant_id",
        (FileKey(Network.ED2K, ed2k_hash).file_id, sid, name, role, key.digest()),
    ).fetchone()
    variant_id: int = row[0]
    return variant_id


def insert_stage4_range(
    connection: sqlite3.Connection,
    variant_id: int,
    first_seen_at: int,
    last_seen_at: int,
    *,
    node_id: str = "n1",
    received_bytes: int = 0,
    transfer_counter: int = 0,
) -> None:
    """A ``source_ranges`` row of version 10."""
    connection.execute(
        "INSERT INTO source_ranges (variant_id, node_id, first_seen_at, last_seen_at,"
        " received_bytes, transfer_counter) VALUES (?, ?, ?, ?, ?, ?)",
        (variant_id, node_id, first_seen_at, last_seen_at, received_bytes, transfer_counter),
    )


def insert_v11_observation(
    connection: sqlite3.Connection,
    ed2k_hash: str,
    filename: str,
    *,
    observed_at: int = 10,
    media_length_sec: int | None = None,
) -> None:
    """An observation of versions 8 to 11, before 0012 renamed ``media_length_sec``."""
    variant = (FileKey(Network.ED2K, ed2k_hash).file_id, filename, 100, media_length_sec)
    key = content_hash(*variant, None, "[]", "keroro", "n1")
    connection.execute(
        "INSERT INTO observation_variants (file_id, filename, size_bytes, media_length_sec,"
        " raw_meta, keyword, node_id, content_hash) VALUES (?, ?, ?, ?, '[]', 'keroro', 'n1', ?)",
        (*variant, key),
    )
    connection.execute(
        "INSERT INTO observations (variant_id, observed_at, source_count)"
        " SELECT variant_id, ?, 1 FROM observation_variants WHERE content_hash = ?",
        (observed_at, key),
    )


def insert_v11_source_point(
    connection: sqlite3.Connection,
    ed2k_hash: str,
    user_hash: str,
    *,
    directly_reachable: bool,
    transfer_counter: int,
) -> None:
    """A ``source_variants`` row of version 11 and one point of it, before 0012's renames."""
    key = hashlib.blake2b(repr((ed2k_hash, user_hash)).encode(), digest_size=16).digest()
    row = connection.execute(
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
    connection.execute(
        "INSERT INTO source_observations (variant_id, observed_at, transfer_counter)"
        " VALUES (?, 20, ?)",
        (row[0], transfer_counter),
    )
