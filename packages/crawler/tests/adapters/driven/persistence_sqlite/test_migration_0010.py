"""Catalog 0010, pinned at version 10: stage 4's source tables, CHECKs and triggers."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from p2pwatch.domain.source import SourceRole
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import (
    insert_stage4_range,
    insert_stage4_variant,
    open_catalog_at,
)
from tests.support.catalog_rows import file_id, insert_file, insert_source

_FILE, _USER = "a" * 32, "1f2e" * 8
_GROWS = "source_ranges only grows its latest range"
_RANGE_COLUMNS = (
    "variant_id",
    "node_id",
    "first_seen_at",
    "last_seen_at",
    "received_bytes",
    "transfer_counter",
)


@pytest.fixture
def catalog(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_catalog_at(tmp_path / "catalog.db", version=10)
    insert_file(connection, native_id=_FILE)
    insert_source(connection, user_hash=_USER)
    yield connection
    connection.close()


@pytest.fixture
def ranged(catalog: sqlite3.Connection) -> sqlite3.Connection:
    """Variant 1 (``queued``) with one range on ``n1``, 10 to 20; variant 2 (``sending``)."""
    insert_stage4_variant(catalog, native_id=_FILE, user_hash=_USER)
    insert_stage4_variant(catalog, native_id=_FILE, user_hash=_USER, role="sending")
    insert_stage4_range(
        catalog,
        variant_id=1,
        first_seen_at=10,
        last_seen_at=20,
        received_bytes=5,
        transfer_counter=7,
    )
    return catalog


def _ranges(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return rows(
        connection,
        sql=f"SELECT {', '.join(_RANGE_COLUMNS)} FROM source_ranges"
        " ORDER BY variant_id, node_id, first_seen_at",
    )


def _range(*values: object) -> dict[str, object]:
    return dict(zip(_RANGE_COLUMNS, values, strict=True))


# --- The CHECKs of D17's table ---


@pytest.mark.parametrize(
    ("network", "native_id"),
    [("kad", "b" * 32), ("ed2k", "B" * 32), ("ed2k", "b" * 31), ("ed2k", "g" * 32)],
)
def test_a_source_of_an_unknown_network_or_not_32_lowercase_hex_on_ed2k_is_refused(
    *, catalog: sqlite3.Connection, network: str, native_id: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        catalog.execute("INSERT INTO sources VALUES (?, ?, ?)", (b"\x01" * 16, network, native_id))


def test_every_role_of_the_domain_is_accepted(catalog: sqlite3.Connection) -> None:
    for role in SourceRole:
        insert_stage4_variant(catalog, native_id=_FILE, user_hash=_USER, role=role)
    assert rows(catalog, sql="SELECT count(*) AS variant_count FROM source_variants") == [
        {"variant_count": len(SourceRole)}
    ]


def test_a_variant_of_an_unknown_role_is_refused(catalog: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        insert_stage4_variant(catalog, native_id=_FILE, user_hash=_USER, role="downloading")


def test_a_variant_without_identity_is_kept(catalog: sqlite3.Connection) -> None:
    insert_stage4_variant(catalog, native_id=_FILE, user_hash=None)
    assert rows(catalog, sql="SELECT file_id, source_id FROM source_variants") == [
        {"file_id": file_id(_FILE), "source_id": None}
    ]


@pytest.mark.parametrize(
    ("last_seen_at", "received_bytes"), [(9, 0), (10, -1)], ids=["ends-before", "negative"]
)
def test_a_range_ending_before_it_starts_or_with_negative_bytes_is_refused(
    *, catalog: sqlite3.Connection, last_seen_at: int, received_bytes: int
) -> None:
    insert_stage4_variant(catalog, native_id=_FILE, user_hash=_USER)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        insert_stage4_range(
            catalog,
            variant_id=1,
            first_seen_at=10,
            last_seen_at=last_seen_at,
            received_bytes=received_bytes,
        )


# --- Stage 4's D5 rule for source_ranges ---


def test_the_latest_range_grows_all_three_columns(ranged: sqlite3.Connection) -> None:
    ranged.execute(
        "UPDATE source_ranges SET last_seen_at = 50, received_bytes = 9, transfer_counter = 11"
    )
    assert _ranges(ranged) == [_range(1, "n1", 10, 50, 9, 11)]


@pytest.mark.parametrize(
    "assignment",
    [
        "variant_id = 2",
        "node_id = 'n2'",
        "first_seen_at = 11",
        "first_seen_at = 9",
        "last_seen_at = 19",
        "received_bytes = 4",
        "transfer_counter = 6",
    ],
)
def test_an_update_that_moves_a_key_or_lowers_a_value_is_refused(
    *, ranged: sqlite3.Connection, assignment: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError, match=_GROWS):
        ranged.execute(f"UPDATE source_ranges SET {assignment}")
    assert _ranges(ranged) == [_range(1, "n1", 10, 20, 5, 7)]


@pytest.mark.parametrize(
    "assignment", ["last_seen_at = 25", "received_bytes = 6", "transfer_counter = 8"]
)
def test_a_range_that_a_later_one_follows_does_not_grow(
    *, ranged: sqlite3.Connection, assignment: str
) -> None:
    insert_stage4_range(ranged, variant_id=1, first_seen_at=30, last_seen_at=40)
    with pytest.raises(sqlite3.IntegrityError, match=_GROWS):
        ranged.execute(f"UPDATE source_ranges SET {assignment} WHERE first_seen_at = 10")


def test_a_later_range_of_another_node_or_variant_does_not_stop_growth(
    ranged: sqlite3.Connection,
) -> None:
    insert_stage4_range(ranged, variant_id=1, first_seen_at=30, last_seen_at=40, node_id="n2")
    insert_stage4_range(ranged, variant_id=2, first_seen_at=30, last_seen_at=40)
    ranged.execute(
        "UPDATE source_ranges SET last_seen_at = 25 WHERE variant_id = 1 AND node_id = 'n1'"
    )
    assert _ranges(ranged)[0] == _range(1, "n1", 10, 25, 5, 7)


def test_an_update_to_the_same_values_passes_even_when_a_later_range_follows(
    ranged: sqlite3.Connection,
) -> None:
    insert_stage4_range(ranged, variant_id=1, first_seen_at=30, last_seen_at=40)
    ranged.execute(
        "UPDATE source_ranges SET variant_id = variant_id, node_id = node_id,"
        " first_seen_at = first_seen_at, last_seen_at = last_seen_at,"
        " received_bytes = received_bytes, transfer_counter = transfer_counter"
    )
    assert _ranges(ranged) == [
        _range(1, "n1", 10, 20, 5, 7),
        _range(1, "n1", 30, 40, 0, 0),
    ]


def test_a_range_is_never_deleted(ranged: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError, match=_GROWS):
        ranged.execute("DELETE FROM source_ranges")
