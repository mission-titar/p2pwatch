"""The catalog's guarantees ENFORCED IN SQL (spec data-model §3): SCHEMA properties, not the code's.

Every table in ``catalog.db`` carries a ``BEFORE UPDATE`` and a ``BEFORE DELETE`` trigger →
``RAISE(ABORT, '<table> is append-only')``, and ``session_received_bytes`` a sign ``CHECK``.
Verified here by DIRECT statements on the connection (as a third-party tool would): a violation
surfaces as ``sqlite3.IntegrityError`` (the REAL class observed, SQLite 3.47.1).
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

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
