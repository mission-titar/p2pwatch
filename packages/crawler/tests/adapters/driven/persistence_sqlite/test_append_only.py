"""The catalog's guarantees ENFORCED IN SQL (spec data-model §3): SCHEMA properties, not the code's.

Every table in ``catalog.db`` carries a ``BEFORE UPDATE`` and a ``BEFORE DELETE`` trigger →
``RAISE(ABORT, '<table> is append-only')``; each quantity a sign ``CHECK``, ``tier`` and
``connectable`` their closed sets, each ``*_micros`` the range of ``datetime``.
Verified here by DIRECT statements on the connection (as a third-party tool would): a violation
surfaces as ``sqlite3.IntegrityError`` (the REAL class observed, SQLite 3.47.1).
"""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_catalog
from tests.support.catalog_rows import (
    insert_decision,
    insert_file,
    insert_observation,
    insert_source,
    insert_source_point,
    insert_source_variant,
)

# Canonical 32-char lowercase hex hash (satisfies the eD2k CHECK on files.native_id).
_HASH = "a" * 32

# The UPDATE that MUST fail, per table.
_UPDATES = {
    "files": "UPDATE files SET size_bytes = 2",
    "observation_variants": "UPDATE observation_variants SET filename = 'autre'",
    "observations": "UPDATE observations SET source_count = 2",
    "match_decisions": "UPDATE match_decisions SET tier = 'notify'",
    "sources": f"UPDATE sources SET native_id = '{'b' * 32}'",
    "source_variants": "UPDATE source_variants SET name = 'autre'",
    "source_observations": "UPDATE source_observations SET session_received_bytes = 2",
}


@pytest.fixture
def seeded_catalog(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_catalog(tmp_path / "catalog.db")
    insert_file(connection, native_id=_HASH, size_bytes=1)
    insert_observation(connection, native_id=_HASH, filename="f")
    insert_decision(connection, native_id=_HASH, target_id="062A", tier="download")
    insert_source(connection, user_hash=_HASH)
    insert_source_point(
        connection,
        variant_id=insert_source_variant(connection, native_id=_HASH, user_hash=_HASH),
        observed_at_micros=1,
    )
    yield connection
    connection.close()


@pytest.mark.parametrize("table", sorted(_UPDATES))
def test_direct_update_is_rejected_by_the_database(
    *, seeded_catalog: sqlite3.Connection, table: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError, match=f"{table} is append-only"):
        seeded_catalog.execute(_UPDATES[table])


@pytest.mark.parametrize("table", sorted(_UPDATES))
def test_direct_delete_is_rejected_by_the_database(
    *, seeded_catalog: sqlite3.Connection, table: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError, match=f"{table} is append-only"):
        seeded_catalog.execute(f"DELETE FROM {table}")


def test_insert_remains_allowed_on_every_table(seeded_catalog: sqlite3.Connection) -> None:
    # Append-only = you can ALWAYS add (the seed INSERT already succeeded);
    # here we prove a SECOND insert passes too (the triggers only block U/D).
    insert_file(seeded_catalog, native_id="b" * 32, size_bytes=2)
    assert rows(seeded_catalog, sql="SELECT count(*) AS file_count FROM files") == [
        {"file_count": 2}
    ]


def test_a_negative_session_received_bytes_is_refused_by_the_database(
    seeded_catalog: sqlite3.Connection,
) -> None:
    variant_id = insert_source_variant(
        seeded_catalog, native_id=_HASH, user_hash=_HASH, node_id="n2"
    )
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        insert_source_point(
            seeded_catalog, variant_id=variant_id, observed_at_micros=1, session_received_bytes=-1
        )


_MIN_MICROS = instant_to_micros(datetime.min.replace(tzinfo=UTC))
_MAX_MICROS = instant_to_micros(datetime.max.replace(tzinfo=UTC))
_VARIANT = (
    "INSERT INTO observation_variants (file_id, filename, size_bytes, duration_seconds,"
    " bitrate_kbps, raw_metadata, keyword, node_id, content_hash)"
    " SELECT file_id, 'f', {size_bytes}, {duration_seconds}, {bitrate_kbps}, '{{}}', 'k', 'n',"
    " randomblob(16) FROM files"
)
_DECISION = (
    "INSERT INTO match_decisions (file_id, target_id, rule_name, tier, decided_at_micros, node_id)"
    " SELECT file_id, '062A', 'r', {tier}, {decided_at_micros}, 'n' FROM files"
)


def _variant_holding(column: str) -> str:
    return _VARIANT.format_map(
        {"size_bytes": "1", "duration_seconds": "NULL", "bitrate_kbps": "NULL", column: "?1"}
    )


# An INSERT per column of a CHECK, its value bound to ?1.
_INSERT_BY_COLUMN = {
    "files.size_bytes": f"INSERT INTO files VALUES (randomblob(16), 'ed2k', '{'b' * 32}', ?1)",
    "observation_variants.size_bytes": _variant_holding("size_bytes"),
    "observation_variants.duration_seconds": _variant_holding("duration_seconds"),
    "observation_variants.bitrate_kbps": _variant_holding("bitrate_kbps"),
    "observations.source_count": "INSERT INTO observations VALUES (1, 0, ?1)",
    "observations.observed_at_micros": "INSERT INTO observations VALUES (1, ?1, 0)",
    "match_decisions.tier": _DECISION.format(tier="?1", decided_at_micros="0"),
    "match_decisions.decided_at_micros": _DECISION.format(
        tier="'download'", decided_at_micros="?1"
    ),
    "source_variants.connectable": (
        "INSERT INTO source_variants (file_id, role, connectable, raw_metadata, node_id,"
        " content_hash) SELECT file_id, 'queued', ?1, '{}', 'n', randomblob(16) FROM files"
    ),
    "source_observations.observed_at_micros": "INSERT INTO source_observations VALUES (1, ?1, 0)",
}
_SIGN_COLUMNS = (
    "files.size_bytes",
    "observation_variants.size_bytes",
    "observation_variants.duration_seconds",
    "observation_variants.bitrate_kbps",
    "observations.source_count",
)
_MICROS_COLUMNS = (
    "observations.observed_at_micros",
    "match_decisions.decided_at_micros",
    "source_observations.observed_at_micros",
)
_REFUSED = [
    *((column, -1) for column in _SIGN_COLUMNS),
    ("match_decisions.tier", "rejected"),
    ("source_variants.connectable", 2),
    *((column, _MIN_MICROS - 1) for column in _MICROS_COLUMNS),
    *((column, _MAX_MICROS + 1) for column in _MICROS_COLUMNS),
]
_ACCEPTED = [
    *((column, 0) for column in _SIGN_COLUMNS),
    ("observation_variants.duration_seconds", None),
    ("observation_variants.bitrate_kbps", None),
    *(("match_decisions.tier", tier) for tier in ("catalog", "notify", "download", "retracted")),
    *(("source_variants.connectable", connectable) for connectable in (0, 1, None)),
    *((column, _MIN_MICROS) for column in _MICROS_COLUMNS),
    *((column, _MAX_MICROS) for column in _MICROS_COLUMNS),
]


@pytest.mark.parametrize(("column", "value"), _REFUSED)
def test_a_value_out_of_its_column_s_check_is_refused_by_the_database(
    *, seeded_catalog: sqlite3.Connection, column: str, value: object
) -> None:
    with pytest.raises(
        sqlite3.IntegrityError, match=f"CHECK constraint failed: .*{column.split('.')[1]}"
    ):
        seeded_catalog.execute(_INSERT_BY_COLUMN[column], (value,))


@pytest.mark.parametrize(("column", "value"), _ACCEPTED)
def test_a_value_within_its_column_s_check_is_accepted_by_the_database(
    *, seeded_catalog: sqlite3.Connection, column: str, value: object
) -> None:
    assert seeded_catalog.execute(_INSERT_BY_COLUMN[column], (value,)).rowcount == 1
