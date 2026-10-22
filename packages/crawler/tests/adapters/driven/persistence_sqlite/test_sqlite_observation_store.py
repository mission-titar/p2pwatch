import dataclasses
import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog
from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.variants import content_hash, iso_to_micros
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import FileObservation, ReportedFile, fold_raw_metadata
from tests.support.catalog_rows import count_observations, insert_file

_HASH = "31d6cfe0d16ae931b73c59d7e0c089c0"
_HASH_B = "b" * 32
_KEY = FileKey(Network.ED2K, _HASH)
_NODE = "11111111-2222-3333-4444-555555555555"
_T0 = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
_T0_ISO = "2026-06-11T12:00:00.000000+00:00"


def _reported_file(
    *,
    filename: str = "Keroro 062A.avi",
    size_bytes: int = 234567890,
    duration_seconds: int | None = None,
    bitrate_kbps: int | None = None,
) -> ReportedFile:
    # raw_metadata with a DUPLICATE, wire order, non-ASCII and the fold's native types.
    return ReportedFile(
        file=_KEY,
        filename=filename,
        size_bytes=size_bytes,
        source_count=5,
        keyword="keroro",
        duration_seconds=duration_seconds,
        bitrate_kbps=bitrate_kbps,
        raw_metadata=fold_raw_metadata(
            (("0x0308", "0"), ("0x0308", "0"), ("0x0999", "mystère")), None, None, 2
        ),
    )


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(tmp_path / "catalog.db")
    yield catalog
    catalog.close()


@pytest.fixture
def observation_store(connection: sqlite3.Connection) -> SqliteObservationStore:
    return SqliteObservationStore(connection)


def test_record_observation_round_trip(
    observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    observation_store.record_observation(FileObservation(_reported_file(), _T0), _NODE)
    file_row = connection.execute("SELECT * FROM files").fetchone()
    assert file_row == (_KEY.file_id, "ed2k", _HASH, 234567890)
    variant = (
        _KEY.file_id,
        "Keroro 062A.avi",
        234567890,
        None,
        None,
        '[["0x0308", "0"], ["0x0308", "0"], ["0x0999", "mystère"], ["codec", null],'
        ' ["file_type", null], ["complete_source_count", 2]]',
        "keroro",
        _NODE,
    )
    row = connection.execute(
        "SELECT file_id, filename, size_bytes, duration_seconds, bitrate_kbps, raw_metadata,"
        " keyword, node_id, content_hash FROM observation_variants"
    ).fetchone()
    assert row == (*variant, content_hash(*variant))
    observation = connection.execute("SELECT observed_at, source_count FROM observations")
    assert observation.fetchall() == [(iso_to_micros(_T0_ISO), 5)]


def test_raw_metadata_preserves_order_duplicates_and_non_ascii(
    observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    observation_store.record_observation(FileObservation(_reported_file(), _T0), _NODE)
    stored = connection.execute("SELECT raw_metadata FROM observation_variants").fetchone()[0]
    assert "mystère" in stored  # ensure_ascii=False: the accent is stored AS IS
    assert json.loads(stored)[:3] == [["0x0308", "0"], ["0x0308", "0"], ["0x0999", "mystère"]]


def test_record_observation_twice_first_seen_wins_in_files(
    observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    observation_store.record_observation(FileObservation(_reported_file(), _T0), _NODE)
    # Same hash, DIFFERENT size and name (hostile input, deviation 1 spec §5).
    observation_store.record_observation(
        FileObservation(_reported_file(filename="leurre.avi", size_bytes=999), _T0), _NODE
    )
    assert connection.execute("SELECT size_bytes FROM files").fetchall() == [(234567890,)]
    observed_sizes = connection.execute(
        "SELECT size_bytes FROM observation_variants ORDER BY variant_id"
    ).fetchall()
    assert observed_sizes == [(234567890,), (999,)]  # the anomaly stays VISIBLE


def test_a_variant_seen_again_is_stored_once_with_both_timestamps(
    observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    observation_store.record_observation(FileObservation(_reported_file(), _T0), _NODE)
    observation_store.record_observation(
        FileObservation(_reported_file(), _T0 + timedelta(minutes=1)), _NODE
    )
    assert connection.execute("SELECT count(*) FROM observation_variants").fetchone()[0] == 1
    assert count_observations(connection) == 2


def test_an_observation_equal_in_every_column_is_stored_once(
    observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    observation_store.record_observation(FileObservation(_reported_file(), _T0), _NODE)
    observation_store.record_observation(FileObservation(_reported_file(), _T0), _NODE)
    assert count_observations(connection) == 1


def test_record_observation_with_media_metadata(
    observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    observation_store.record_observation(
        FileObservation(_reported_file(duration_seconds=1474, bitrate_kbps=1200), _T0), _NODE
    )
    row = connection.execute(
        "SELECT duration_seconds, bitrate_kbps FROM observation_variants"
    ).fetchone()
    assert row == (1474, 1200)


def test_record_observation_is_one_transaction(
    observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    # Failure injected on the last INSERT: a TEST trigger makes the observation fail.
    connection.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON observations"
        " WHEN NEW.source_count = 404"
        " BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    with pytest.raises(PersistenceError, match="injected failure"):
        observation_store.record_observation(
            FileObservation(dataclasses.replace(_reported_file(), source_count=404), _T0), _NODE
        )
    # ATOMICITY: the file and its variant were rolled back with the transaction.
    assert connection.execute("SELECT count(*) FROM files").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM observation_variants").fetchone()[0] == 0
    # The store stays USABLE: rollback done, connection out of transaction.
    assert not connection.in_transaction
    observation_store.record_observation(FileObservation(_reported_file(), _T0), _NODE)
    assert count_observations(connection) == 1


def test_record_observation_rejects_non_canonical_hash(
    observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    # INSERT OR IGNORE SILENTLY swallows a CHECK violation (documented SQLite
    # behavior): without Python validation BEFORE the transaction, a non-canonical hash
    # would only survive thanks to the foreign_keys pragma (opaque diagnostic), and a connection
    # without that pragma would commit an ORPHAN observation.
    upper = dataclasses.replace(_reported_file(), file=FileKey(Network.ED2K, _HASH.upper()))
    with pytest.raises(PersistenceError, match="non-canonical eD2k hash"):
        observation_store.record_observation(FileObservation(upper, _T0), _NODE)
    assert connection.execute("SELECT count(*) FROM files").fetchone()[0] == 0
    assert count_observations(connection) == 0


def test_rollback_on_non_sqlite_error_keeps_connection_usable(
    observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    # An isolated surrogate makes the parameter BINDING fail (UnicodeEncodeError, which
    # is NOT a sqlite3.Error): without a rollback on BaseException, the connection
    # would stay in_transaction=True and every later call would fail permanently
    # ("cannot start a transaction within a transaction").
    with pytest.raises(UnicodeEncodeError):
        observation_store.record_observation(
            FileObservation(_reported_file(filename="a\ud800"), _T0), _NODE
        )
    assert not connection.in_transaction
    observation_store.record_observation(FileObservation(_reported_file(), _T0), _NODE)
    assert count_observations(connection) == 1


def test_outer_transaction_survives_record_observation_failure(
    observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    # Nested-transaction contract: the store's BEGIN fails ("cannot start a
    # transaction within a transaction") BEFORE the try → NO rollback is attempted,
    # the OUTER transaction and its pending rows SURVIVE.
    connection.execute("BEGIN")
    insert_file(connection, _HASH, 1)
    with pytest.raises(PersistenceError, match="cannot start a transaction within a transaction"):
        observation_store.record_observation(FileObservation(_reported_file(), _T0), _NODE)
    assert connection.in_transaction  # the outer transaction is INTACT
    assert connection.execute("SELECT count(*) FROM files").fetchone()[0] == 1
    connection.execute("ROLLBACK")
    assert connection.execute("SELECT count(*) FROM files").fetchone()[0] == 0


def test_each_observation_stores_the_node_id_its_call_gives(
    observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    observation_store.record_observation(FileObservation(_reported_file(), _T0), "n1")
    observation_store.record_observation(FileObservation(_reported_file(), _T0), "n2")
    variants = connection.execute("SELECT node_id FROM observation_variants ORDER BY variant_id")
    assert variants.fetchall() == [("n1",), ("n2",)]


def test_read_latest_observation_of_a_file_never_observed_is_none(
    observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    insert_file(connection, _HASH, 1)
    assert observation_store.read_latest_observation(_KEY) is None
