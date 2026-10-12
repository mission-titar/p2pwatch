"""Shared test helpers for the merge script (real catalogs, never ``:memory:``).

WAL requires a real file (``open_catalog`` rejects ``:memory:``): each helper creates a
``catalog.db`` on disk via ``open_catalog`` (schema + append-only triggers), inserts the given
rows (FK: ``files`` before the journals), closes, and returns the path.
"""

import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from p2pwatch.adapters.persistence_sqlite.connection import open_catalog
from tests.catalog_rows import (
    insert_decision,
    insert_file,
    insert_observation,
    insert_source,
    insert_source_range,
    insert_source_variant,
)

# Natural-key reads, a file named by its native id; an observation with its variant's columns.
_ROWS_BY_TABLE: Mapping[str, str] = {
    "files": "SELECT native_id, size_bytes FROM files",
    "observations": (
        "SELECT f.native_id, v.filename, v.size_bytes, v.media_length_sec, v.bitrate_kbps,"
        " v.raw_meta, v.keyword, v.node_id, o.observed_at, o.source_count"
        " FROM files AS f JOIN observation_variants AS v USING (file_id)"
        " JOIN observations AS o USING (variant_id)"
    ),
    "match_decisions": (
        "SELECT f.native_id, d.target_id, d.rule_name, d.tier, d.decided_at, d.node_id"
        " FROM match_decisions AS d JOIN files AS f USING (file_id)"
    ),
    "sources": "SELECT network, native_id FROM sources",
    "source_variants": (
        "SELECT f.native_id, s.native_id, v.name, v.role, v.content_hash"
        " FROM source_variants AS v JOIN files AS f USING (file_id)"
        " LEFT JOIN sources AS s ON s.source_id = v.source_id"
    ),
    "source_ranges": (
        "SELECT v.content_hash, r.node_id, r.first_seen_at, r.last_seen_at, r.received_bytes,"
        " r.transfer_counter FROM source_ranges AS r JOIN source_variants AS v USING (variant_id)"
    ),
}

# One canonical eD2k hash (32 lowercase hex chars) per letter; satisfies the CHECK on files.
HASH_A = "a" * 32
HASH_B = "b" * 32


def hash_for(letter: str) -> str:
    """A canonical 32-char hash repeating ``letter`` (a single hex character)."""
    return letter * 32


def make_catalog(
    path: Path, content: Mapping[str, Sequence[Mapping[str, Any]]] | None = None
) -> Path:
    """Create a real ``catalog.db`` at ``path`` and insert ``content`` (per table, FK order).

    ``content`` maps a table name → rows, each holding its ``tests.catalog_rows`` builder's
    arguments. Returns ``path`` for chaining.
    """
    connection = open_catalog(path)
    try:
        if content is not None:
            for row in content.get("files", ()):
                insert_file(connection, **row)
            for row in content.get("observations", ()):
                insert_observation(connection, **row)
            for row in content.get("match_decisions", ()):
                insert_decision(connection, **row)
            _insert_source_ranges(connection, content.get("source_ranges", ()))
    finally:
        connection.close()
    return path


def _insert_source_ranges(
    connection: sqlite3.Connection, rows: Sequence[Mapping[str, Any]]
) -> None:
    """Each row: its variant's ``ed2k_hash`` and ``user_hash``, then its range's arguments."""
    variants: dict[tuple[str, str | None], int] = {}
    for row in rows:
        ed2k_hash, user_hash = row["ed2k_hash"], row["user_hash"]
        if (ed2k_hash, user_hash) not in variants:
            if user_hash is not None and user_hash not in {key[1] for key in variants}:
                insert_source(connection, user_hash)
            variants[ed2k_hash, user_hash] = insert_source_variant(connection, ed2k_hash, user_hash)
        range_args = {k: v for k, v in row.items() if k not in ("ed2k_hash", "user_hash")}
        insert_source_range(connection, variants[ed2k_hash, user_hash], **range_args)


def stamp_user_version(path: Path, version: int) -> None:
    """Force ``path``'s ``PRAGMA user_version`` to ``version`` (simulate an off-schema DB).

    Uses a RAW ``sqlite3`` connection on purpose: ``open_catalog`` would refuse a DB newer
    than the code, and re-running it would re-stamp the current version. We only rewrite the
    header's version counter (the on-disk schema stays whatever ``make_catalog`` laid down),
    which is exactly what the merge guard reads.
    """
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"PRAGMA user_version = {int(version)}")
        connection.commit()
    finally:
        connection.close()


def count(path: Path, table: str) -> int:
    """Number of rows of ``table`` in the catalog ``path``."""
    connection = open_catalog(path)
    try:
        return int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
    finally:
        connection.close()


def rows_without_id(path: Path, table: str) -> list[tuple[object, ...]]:
    """All rows of ``table`` by their natural key (no local id), sorted."""
    connection = open_catalog(path)
    try:
        cursor = connection.execute(_ROWS_BY_TABLE[table])
        return sorted(cursor.fetchall(), key=lambda row: tuple(str(value) for value in row))
    finally:
        connection.close()


def variant_ids(path: Path) -> list[int]:
    """The (reassigned) ``variant_id`` values, sorted ascending."""
    connection = open_catalog(path)
    try:
        cursor = connection.execute("SELECT variant_id FROM observation_variants ORDER BY 1")
        return [int(row[0]) for row in cursor.fetchall()]
    finally:
        connection.close()
