"""Catalog rows for tests, written and read here only so that a schema change edits one module."""

import hashlib
import sqlite3

from p2pwatch.adapters.driven.persistence_sqlite.variants import content_hash, iso_to_micros
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.source import SourceKey

SEEN_AT = "2026-06-22T10:00:00.000000+00:00"


def file_id(ed2k_hash: str) -> bytes:
    return FileKey(Network.ED2K, ed2k_hash).file_id


def insert_file(conn: sqlite3.Connection, ed2k_hash: str, size_bytes: int = 100) -> None:
    conn.execute(
        "INSERT INTO files (file_id, network, native_id, size_bytes) VALUES (?, 'ed2k', ?, ?)",
        (file_id(ed2k_hash), ed2k_hash, size_bytes),
    )


def insert_observation(
    conn: sqlite3.Connection,
    ed2k_hash: str,
    filename: str,
    *,
    observed_at: str = SEEN_AT,
    size_bytes: int = 100,
    source_count: int = 1,
    duration_seconds: int | None = None,
    bitrate_kbps: int | None = None,
    node_id: str = "n1",
) -> None:
    variant = (
        file_id(ed2k_hash),
        filename,
        size_bytes,
        duration_seconds,
        bitrate_kbps,
        "[]",
        "keroro",
        node_id,
    )
    key = content_hash(*variant)
    conn.execute(
        "INSERT OR IGNORE INTO observation_variants"
        " (file_id, filename, size_bytes, duration_seconds, bitrate_kbps, raw_meta, keyword,"
        " node_id, content_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (*variant, key),
    )
    conn.execute(
        "INSERT INTO observations (variant_id, observed_at, source_count)"
        " SELECT variant_id, ?, ? FROM observation_variants WHERE content_hash = ?",
        (iso_to_micros(observed_at), source_count, key),
    )


def insert_decision(
    conn: sqlite3.Connection,
    ed2k_hash: str,
    target_id: str,
    tier: str,
    *,
    rule_name: str = "rule",
    decided_at: str = SEEN_AT,
    node_id: str = "n1",
) -> None:
    conn.execute(
        "INSERT INTO match_decisions"
        " (file_id, target_id, rule_name, tier, decided_at, node_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (file_id(ed2k_hash), target_id, rule_name, tier, decided_at, node_id),
    )


def source_id(user_hash: str) -> bytes:
    return SourceKey(Network.ED2K, user_hash).source_id


def insert_source(conn: sqlite3.Connection, user_hash: str) -> None:
    conn.execute(
        "INSERT INTO sources (source_id, network, native_id) VALUES (?, 'ed2k', ?)",
        (source_id(user_hash), user_hash),
    )


def insert_source_variant(
    conn: sqlite3.Connection,
    ed2k_hash: str,
    user_hash: str | None,
    *,
    name: str | None = "AnimuseeFMR",
    role: str = "queued",
    contact_point: str | None = None,
    connectable: bool | None = None,
    node_id: str = "n1",
) -> int:
    """The new variant's ``variant_id``; its ``content_hash`` stands in for the writer's."""
    sid = source_id(user_hash) if user_hash is not None else None
    columns = (name, role, contact_point, connectable)
    key = hashlib.blake2b(repr((ed2k_hash, user_hash, *columns, node_id)).encode(), digest_size=16)
    row = conn.execute(
        "INSERT INTO source_variants (file_id, source_id, name, role, contact_point,"
        " connectable, raw_meta, node_id, content_hash)"
        " VALUES (?, ?, ?, ?, ?, ?, '{}', ?, ?) RETURNING variant_id",
        (file_id(ed2k_hash), sid, *columns, node_id, key.digest()),
    ).fetchone()
    variant_id: int = row[0]
    return variant_id


def insert_source_point(
    conn: sqlite3.Connection, variant_id: int, observed_at: int, *, session_received_bytes: int = 0
) -> None:
    conn.execute(
        "INSERT INTO source_observations (variant_id, observed_at, session_received_bytes)"
        " VALUES (?, ?, ?)",
        (variant_id, observed_at, session_received_bytes),
    )


def count_observations(conn: sqlite3.Connection) -> int:
    count: int = conn.execute("SELECT count(*) FROM observations").fetchone()[0]
    return count


def observation_node_ids(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT node_id FROM observation_variants")}


def decision_tiers(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """``(ed2k_hash, tier)`` of every decision, oldest first."""
    rows = conn.execute(
        "SELECT f.native_id, d.tier FROM match_decisions AS d"
        " JOIN files AS f USING (file_id) ORDER BY d.id"
    ).fetchall()
    return [(row[0], row[1]) for row in rows]
