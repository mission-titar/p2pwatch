"""An observation variant's ``content_hash``, and the SQL functions the catalog migrations call.

Changing the serialization changes every stored ``content_hash``: it needs a migration.
"""

import hashlib
import json
import sqlite3
from functools import cache
from typing import Any, Protocol

from p2pwatch.adapters.driven.persistence_sqlite import micros
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import FileId
from p2pwatch.domain.observation import fold_raw_metadata


def content_hash(  # noqa: PLR0917
    file_ref: str | bytes,
    filename: str,
    size_bytes: int,
    duration_seconds: int | None,
    bitrate_kbps: int | None,
    raw_metadata: str,
    keyword: str,
    node_id: str,
) -> bytes:
    """blake2b-128 of the columns as compact JSON, a BLOB ``file_ref`` written as lowercase hex."""
    columns = (
        file_ref.hex() if isinstance(file_ref, bytes) else file_ref,
        filename,
        size_bytes,
        duration_seconds,
        bitrate_kbps,
        raw_metadata,
        keyword,
        node_id,
    )
    canonical = json.dumps(columns, ensure_ascii=False, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode(), digest_size=16).digest()


def file_id(network: str, native_id: str) -> FileId:  # noqa: PLR0917
    """``FileKey.file_id`` for the SQL function; an unknown network raises."""
    return FileKey(Network(network), native_id).file_id


def register_sql_functions(connection: sqlite3.Connection) -> None:
    """Registers ``content_hash``, ``file_id``, ``fold_raw_meta`` and ``iso_to_micros``."""

    # A stored raw_metadata, folded and serialized as record_observation serializes it.
    def fold_stored(  # noqa: PLR0917
        raw_metadata: str, codec: str | None, file_type: str | None, complete: int
    ) -> str:
        return json.dumps(
            fold_raw_metadata(json.loads(raw_metadata), codec, file_type, complete),
            ensure_ascii=False,
        )

    # Memoized for the connection's life, the crawler's included: one entry per variant 0007 wrote.
    create_memoized_function(connection, "content_hash", 8, content_hash)
    # The SQL name keeps its old spelling: migration catalog/0007, which never changes, calls it.
    create_memoized_function(connection, "fold_raw_meta", 4, fold_stored)
    connection.create_function("file_id", 2, file_id, deterministic=True)
    # Never memoized: every observation has its own stamp, the memo would hold them all.
    # The migrations' reference, the one sanctioned: remove_migration_sql_functions drops it after.
    iso_to_micros = micros.iso_to_micros  # type: ignore[deprecated]
    connection.create_function("iso_to_micros", 1, iso_to_micros, deterministic=True)


def remove_migration_sql_functions(connection: sqlite3.Connection) -> None:
    """Removes ``iso_to_micros``, which only the migrations call, so a store's SQL cannot."""
    # create_function(..., None) registers None; this call hands SQLite the NULLs that delete it.
    connection.create_window_function("iso_to_micros", 1, None)


class SqlFunction(Protocol):
    def __call__(self, *arguments: Any, **keywords: Any) -> str | bytes: ...


def create_memoized_function(
    connection: sqlite3.Connection,
    name: str,
    argument_count: int,
    function: SqlFunction,
) -> None:
    """Registers ``function`` as the SQL function ``name``, called once per distinct arguments."""
    connection.create_function(name, argument_count, cache(function), deterministic=True)
