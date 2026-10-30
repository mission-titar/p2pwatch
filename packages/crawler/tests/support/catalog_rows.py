"""Catalog rows for tests, written and read here only so that a schema change edits one module."""

import hashlib
import sqlite3
from datetime import datetime

from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from p2pwatch.adapters.driven.persistence_sqlite.variants import content_hash
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import FileId, SourceId
from p2pwatch.domain.source import SourceKey
from tests.support.adapters.driven.persistence_sqlite.named_row import rows

SEEN_AT = "2026-06-22T10:00:00.000000+00:00"


def file_id(native_id: str) -> FileId:
    return FileKey(network=Network.ED2K, native_id=native_id).file_id


def insert_file(connection: sqlite3.Connection, native_id: str, size_bytes: int = 100) -> None:
    connection.execute(
        "INSERT INTO files (file_id, network, native_id, size_bytes) VALUES (?, 'ed2k', ?, ?)",
        (file_id(native_id), native_id, size_bytes),
    )


def insert_observation(
    connection: sqlite3.Connection,
    native_id: str,
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
        file_id(native_id),
        filename,
        size_bytes,
        duration_seconds,
        bitrate_kbps,
        "[]",
        "keroro",
        node_id,
    )
    key = content_hash(*variant)
    connection.execute(
        "INSERT OR IGNORE INTO observation_variants"
        " (file_id, filename, size_bytes, duration_seconds, bitrate_kbps, raw_metadata, keyword,"
        " node_id, content_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (*variant, key),
    )
    connection.execute(
        "INSERT INTO observations (variant_id, observed_at_micros, source_count)"
        " SELECT variant_id, ?, ? FROM observation_variants WHERE content_hash = ?",
        (instant_to_micros(datetime.fromisoformat(observed_at)), source_count, key),
    )


def insert_decision(
    connection: sqlite3.Connection,
    native_id: str,
    target_id: str,
    tier: str,
    *,
    rule_name: str = "rule",
    decided_at: str = SEEN_AT,
    node_id: str = "n1",
) -> None:
    connection.execute(
        "INSERT INTO match_decisions"
        " (file_id, target_id, rule_name, tier, decided_at_micros, node_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            file_id(native_id),
            target_id,
            rule_name,
            tier,
            instant_to_micros(datetime.fromisoformat(decided_at)),
            node_id,
        ),
    )


def source_id(user_hash: str) -> SourceId:
    return SourceKey(network=Network.ED2K, native_id=user_hash).source_id


def insert_source(connection: sqlite3.Connection, user_hash: str) -> None:
    connection.execute(
        "INSERT INTO sources (source_id, network, native_id) VALUES (?, 'ed2k', ?)",
        (source_id(user_hash), user_hash),
    )


def insert_source_variant(
    connection: sqlite3.Connection,
    native_id: str,
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
    key = hashlib.blake2b(repr((native_id, user_hash, *columns, node_id)).encode(), digest_size=16)
    [variant] = rows(
        connection,
        "INSERT INTO source_variants (file_id, source_id, name, role, contact_point,"
        " connectable, raw_metadata, node_id, content_hash)"
        " VALUES (?, ?, ?, ?, ?, ?, '{}', ?, ?) RETURNING variant_id",
        (file_id(native_id), sid, *columns, node_id, key.digest()),
    )
    variant_id: int = variant["variant_id"]
    return variant_id


def insert_source_point(
    connection: sqlite3.Connection,
    variant_id: int,
    observed_at_micros: int,
    *,
    session_received_bytes: int = 0,
) -> None:
    connection.execute(
        "INSERT INTO source_observations (variant_id, observed_at_micros, session_received_bytes)"
        " VALUES (?, ?, ?)",
        (variant_id, observed_at_micros, session_received_bytes),
    )


def count_observations(connection: sqlite3.Connection) -> int:
    [count] = rows(connection, "SELECT count(*) AS observation_count FROM observations")
    observation_count: int = count["observation_count"]
    return observation_count


def count_decisions(connection: sqlite3.Connection) -> int:
    [count] = rows(connection, "SELECT count(*) AS decision_count FROM match_decisions")
    decision_count: int = count["decision_count"]
    return decision_count


def observation_node_ids(connection: sqlite3.Connection) -> set[str]:
    variants = rows(connection, "SELECT node_id FROM observation_variants")
    return {variant["node_id"] for variant in variants}


def decision_node_ids(connection: sqlite3.Connection) -> set[str]:
    return {
        decision["node_id"] for decision in rows(connection, "SELECT node_id FROM match_decisions")
    }


def source_variant_node_ids(connection: sqlite3.Connection) -> set[str]:
    return {
        variant["node_id"] for variant in rows(connection, "SELECT node_id FROM source_variants")
    }


def decision_tiers(connection: sqlite3.Connection) -> list[tuple[str, str]]:
    """``(native_id, tier)`` of every decision, oldest first."""
    decisions = rows(
        connection,
        "SELECT f.native_id, d.tier FROM match_decisions AS d"
        " JOIN files AS f USING (file_id) ORDER BY d.id",
    )
    return [(decision["native_id"], decision["tier"]) for decision in decisions]
