import hashlib
import sqlite3
from importlib import resources
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite.migration_scripts import Migration, load_scripts
from p2pwatch.adapters.driven.persistence_sqlite.variants import content_hash
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.source import SourceKey
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    database_opener,
    database_opener_setting,
)

_MIGRATIONS = resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations"


def open_catalog_at(path: Path, *, version: int) -> sqlite3.Connection:
    """A catalog.db migrated up to ``version`` only, as an older release left it."""
    return database_opener().open(path, scripts=_scripts_up_to("catalog", version=version))


def open_catalog_forcing_secure_delete_at(path: Path, *, version: int) -> sqlite3.Connection:
    """The same, ``secure_delete`` ON: stands for the image's SQLite, which compiles it in."""
    opener = database_opener_setting("PRAGMA secure_delete = ON")
    return opener.open(path, scripts=_scripts_up_to("catalog", version=version))


def open_local_at(path: Path, *, version: int) -> sqlite3.Connection:
    """The same for a local.db."""
    return database_opener().open(path, scripts=_scripts_up_to("local", version=version))


def _scripts_up_to(database: str, *, version: int) -> tuple[Migration, ...]:
    scripts = load_scripts(_MIGRATIONS / database)
    return tuple(script for script in scripts if script.version <= version)


def insert_stage4_variant(
    connection: sqlite3.Connection,
    *,
    native_id: str,
    user_hash: str | None,
    name: str | None = "AnimuseeFMR",
    role: str = "queued",
) -> int:
    """A ``source_variants`` row of version 10, which has no ``node_id``; its ``variant_id``."""
    sid = (
        None
        if user_hash is None
        else SourceKey(network=Network.ED2K, native_id=user_hash).source_id
    )
    key = hashlib.blake2b(repr((native_id, user_hash, name, role)).encode(), digest_size=16)
    [variant] = rows(
        connection,
        sql="INSERT INTO source_variants (file_id, source_id, name, role, raw_meta, content_hash)"
        " VALUES (?, ?, ?, ?, '{}', ?) RETURNING variant_id",
        parameters=(
            FileKey(network=Network.ED2K, native_id=native_id).file_id,
            sid,
            name,
            role,
            key.digest(),
        ),
    )
    variant_id: int = variant["variant_id"]
    return variant_id


def insert_stage4_range(
    connection: sqlite3.Connection,
    *,
    variant_id: int,
    first_seen_at: int,
    last_seen_at: int,
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
    *,
    native_id: str,
    filename: str,
    observed_at: int = 10,
    media_length_sec: int | None = None,
) -> None:
    """An observation of versions 8 to 11, before 0012 renamed ``media_length_sec``."""
    variant = (
        FileKey(network=Network.ED2K, native_id=native_id).file_id,
        filename,
        100,
        media_length_sec,
    )
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
    *,
    native_id: str,
    user_hash: str,
    directly_reachable: bool,
    transfer_counter: int,
) -> None:
    """A ``source_variants`` row of version 11 and one point of it, before 0012's renames."""
    key = hashlib.blake2b(repr((native_id, user_hash)).encode(), digest_size=16).digest()
    [variant] = rows(
        connection,
        sql="INSERT INTO source_variants (file_id, source_id, name, role, directly_reachable,"
        " raw_meta, node_id, content_hash)"
        " VALUES (?, ?, 'AnimuseeFMR', 'sending', ?, '{}', 'n1', ?) RETURNING variant_id",
        parameters=(
            FileKey(network=Network.ED2K, native_id=native_id).file_id,
            SourceKey(network=Network.ED2K, native_id=user_hash).source_id,
            directly_reachable,
            key,
        ),
    )
    connection.execute(
        "INSERT INTO source_observations (variant_id, observed_at, transfer_counter)"
        " VALUES (?, 20, ?)",
        (variant["variant_id"], transfer_counter),
    )


def insert_v12_observation(
    connection: sqlite3.Connection, *, native_id: str, filename: str, observed_at: int = 10
) -> None:
    """An observation of version 12, before 0013 renamed ``raw_meta``."""
    variant = (FileKey(network=Network.ED2K, native_id=native_id).file_id, filename, 100, None)
    key = content_hash(*variant, None, '[["codec", "xvid"]]', "keroro", "n1")
    connection.execute(
        "INSERT INTO observation_variants (file_id, filename, size_bytes, duration_seconds,"
        " raw_meta, keyword, node_id, content_hash)"
        " VALUES (?, ?, ?, ?, '[[\"codec\", \"xvid\"]]', 'keroro', 'n1', ?)",
        (*variant, key),
    )
    connection.execute(
        "INSERT INTO observations (variant_id, observed_at, source_count)"
        " SELECT variant_id, ?, 1 FROM observation_variants WHERE content_hash = ?",
        (observed_at, key),
    )


def insert_v12_source_point(
    connection: sqlite3.Connection, *, native_id: str, user_hash: str
) -> None:
    """A ``source_variants`` row of version 12 and one point of it, before 0013's rename."""
    key = hashlib.blake2b(repr((native_id, user_hash)).encode(), digest_size=16).digest()
    [variant] = rows(
        connection,
        sql="INSERT INTO source_variants (file_id, source_id, name, role, connectable,"
        " raw_meta, node_id, content_hash)"
        " VALUES (?, ?, 'AnimuseeFMR', 'sending', 1, '{\"version\": \"2.3.3\"}', 'n1', ?)"
        " RETURNING variant_id",
        parameters=(
            FileKey(network=Network.ED2K, native_id=native_id).file_id,
            SourceKey(network=Network.ED2K, native_id=user_hash).source_id,
            key,
        ),
    )
    connection.execute(
        "INSERT INTO source_observations (variant_id, observed_at, session_received_bytes)"
        " VALUES (?, 20, 7)",
        (variant["variant_id"],),
    )


def insert_v13_observation(
    connection: sqlite3.Connection, *, native_id: str, filename: str
) -> None:
    """An observation of version 13, before 0014 renamed ``observed_at``."""
    variant = (FileKey(network=Network.ED2K, native_id=native_id).file_id, filename, 100, None)
    key = content_hash(*variant, None, "[]", "keroro", "n1")
    connection.execute(
        "INSERT INTO observation_variants (file_id, filename, size_bytes, duration_seconds,"
        " raw_metadata, keyword, node_id, content_hash)"
        " VALUES (?, ?, ?, ?, '[]', 'keroro', 'n1', ?)",
        (*variant, key),
    )
    connection.execute(
        "INSERT INTO observations (variant_id, observed_at, source_count)"
        " SELECT variant_id, 1781258400123456, 1 FROM observation_variants"
        " WHERE content_hash = ?",
        (key,),
    )


def insert_v13_source_point(connection: sqlite3.Connection, *, variant_id: int) -> None:
    """A point of version 13 on ``variant_id``, before 0014 renamed ``observed_at``."""
    connection.execute(
        "INSERT INTO source_observations (variant_id, observed_at, session_received_bytes)"
        " VALUES (?, 1781258400654321, 7)",
        (variant_id,),
    )


def insert_v14_decision(
    connection: sqlite3.Connection,
    *,
    native_id: str,
    decision_id: int | None = None,
    decided_at: str = "2026-06-22T10:00:00.000000+00:00",
) -> None:
    """A decision of versions 8 to 14, before 0015 stored ``decided_at`` as micros."""
    connection.execute(
        "INSERT INTO match_decisions (id, file_id, target_id, rule_name, tier, decided_at, node_id)"
        " VALUES (?, ?, '062A', 'exact_062a', 'download', ?, 'n1')",
        (decision_id, FileKey(network=Network.ED2K, native_id=native_id).file_id, decided_at),
    )
