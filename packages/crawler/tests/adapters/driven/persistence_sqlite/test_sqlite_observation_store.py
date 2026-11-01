import dataclasses
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.variants import content_hash
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Keyword, NodeId
from p2pwatch.domain.observation import FileObservation, ReportedFile, fold_raw_metadata
from tests.contracts.application.ports.driven.observation_store_contract import (
    ObservationStoreContract,
)
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_catalog
from tests.support.catalog_rows import count_observations, insert_file

_HASH = "31d6cfe0d16ae931b73c59d7e0c089c0"
_HASH_B = "b" * 32
_KEY = FileKey(network=Network.ED2K, native_id=_HASH)
_NODE_ID = NodeId("11111111-2222-3333-4444-555555555555")
_T0 = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)


def _reported_file(
    *,
    filename: str = "Keroro 062A.avi",
    size_bytes: int = 234567890,
    duration_seconds: int | None = None,
    bitrate_kbps: int | None = None,
) -> ReportedFile:
    # raw_metadata with non-ASCII, a nested object and the fold's native types.
    return ReportedFile(
        file=_KEY,
        filename=filename,
        size_bytes=size_bytes,
        source_count=5,
        keyword=Keyword("keroro"),
        duration_seconds=duration_seconds,
        bitrate_kbps=bitrate_kbps,
        raw_metadata=fold_raw_metadata(
            {"0x0999": "mystère", "0x0308": "0", "media": {"title": "Keroro"}},
            codec=None,
            file_type=None,
            complete_source_count=2,
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


class TestSqliteObservationStore(ObservationStoreContract):
    @pytest.fixture
    def writer(self, observation_store: SqliteObservationStore) -> SqliteObservationStore:
        return observation_store

    @pytest.fixture
    def reader(self, observation_store: SqliteObservationStore) -> SqliteObservationStore:
        return observation_store


def _file_count(connection: sqlite3.Connection) -> int:
    [count] = rows(connection, sql="SELECT count(*) AS file_count FROM files")
    file_count: int = count["file_count"]
    return file_count


def _variant_count(connection: sqlite3.Connection) -> int:
    [count] = rows(connection, sql="SELECT count(*) AS variant_count FROM observation_variants")
    variant_count: int = count["variant_count"]
    return variant_count


def test_record_observation_round_trip(
    *, observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    observation_store.record_observation(
        FileObservation(reported_file=_reported_file(), observed_at=_T0, node_id=_NODE_ID)
    )
    assert rows(connection, sql="SELECT * FROM files") == [
        {"file_id": _KEY.file_id, "network": "ed2k", "native_id": _HASH, "size_bytes": 234567890}
    ]
    variant: dict[str, Any] = {
        "file_id": _KEY.file_id,
        "filename": "Keroro 062A.avi",
        "size_bytes": 234567890,
        "duration_seconds": None,
        "bitrate_kbps": None,
        "raw_metadata": '{"codec": null, "complete_source_count": 2, "file_type": null,'
        ' "unmapped": {"0x0308": "0", "0x0999": "mystère", "media": {"title": "Keroro"}}}',
        "keyword": "keroro",
        "node_id": _NODE_ID,
    }
    columns = {name: value for name, value in variant.items() if name != "file_id"}
    assert rows(
        connection,
        sql="SELECT file_id, filename, size_bytes, duration_seconds, bitrate_kbps, raw_metadata,"
        " keyword, node_id, content_hash FROM observation_variants",
    ) == [{**variant, "content_hash": content_hash(file_ref=_KEY.file_id, **columns)}]
    assert rows(connection, sql="SELECT observed_at_micros, source_count FROM observations") == [
        {"observed_at_micros": instant_to_micros(_T0), "source_count": 5}
    ]


def test_record_observation_twice_first_seen_wins_in_files(
    *, observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    observation_store.record_observation(
        FileObservation(reported_file=_reported_file(), observed_at=_T0, node_id=_NODE_ID)
    )
    # Same hash, DIFFERENT size and name (hostile input, deviation 1 spec §5).
    observation_store.record_observation(
        FileObservation(
            reported_file=_reported_file(filename="leurre.avi", size_bytes=999),
            observed_at=_T0,
            node_id=_NODE_ID,
        )
    )
    assert rows(connection, sql="SELECT size_bytes FROM files") == [{"size_bytes": 234567890}]
    observed_sizes = rows(
        connection, sql="SELECT size_bytes FROM observation_variants ORDER BY variant_id"
    )
    # The anomaly stays VISIBLE.
    assert observed_sizes == [{"size_bytes": 234567890}, {"size_bytes": 999}]


def test_a_variant_seen_again_is_stored_once_with_both_timestamps(
    *, observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    observation_store.record_observation(
        FileObservation(reported_file=_reported_file(), observed_at=_T0, node_id=_NODE_ID)
    )
    observation_store.record_observation(
        FileObservation(
            reported_file=_reported_file(), observed_at=_T0 + timedelta(minutes=1), node_id=_NODE_ID
        )
    )
    assert _variant_count(connection) == 1
    assert count_observations(connection) == 2


def test_an_observation_equal_in_every_column_is_stored_once(
    *, observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    observation_store.record_observation(
        FileObservation(reported_file=_reported_file(), observed_at=_T0, node_id=_NODE_ID)
    )
    observation_store.record_observation(
        FileObservation(reported_file=_reported_file(), observed_at=_T0, node_id=_NODE_ID)
    )
    assert count_observations(connection) == 1


def test_record_observation_with_media_metadata(
    *, observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    observation_store.record_observation(
        FileObservation(
            reported_file=_reported_file(duration_seconds=1474, bitrate_kbps=1200),
            observed_at=_T0,
            node_id=_NODE_ID,
        )
    )
    assert rows(
        connection, sql="SELECT duration_seconds, bitrate_kbps FROM observation_variants"
    ) == [{"duration_seconds": 1474, "bitrate_kbps": 1200}]


def test_record_observation_is_one_transaction(
    *, observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    # Failure injected on the last INSERT: a TEST trigger makes the observation fail.
    connection.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON observations"
        " WHEN NEW.source_count = 404"
        " BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    with pytest.raises(PersistenceError, match="injected failure"):
        observation_store.record_observation(
            FileObservation(
                reported_file=dataclasses.replace(_reported_file(), source_count=404),
                observed_at=_T0,
                node_id=_NODE_ID,
            )
        )
    # ATOMICITY: the file and its variant were rolled back with the transaction.
    assert _file_count(connection) == 0
    assert _variant_count(connection) == 0
    # The store stays USABLE: rollback done, connection out of transaction.
    assert not connection.in_transaction
    observation_store.record_observation(
        FileObservation(reported_file=_reported_file(), observed_at=_T0, node_id=_NODE_ID)
    )
    assert count_observations(connection) == 1


def test_record_observation_rejects_non_canonical_hash(
    *, observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    # INSERT OR IGNORE SILENTLY swallows a CHECK violation (documented SQLite
    # behavior): without Python validation BEFORE the transaction, a non-canonical hash
    # would only survive thanks to the foreign_keys pragma (opaque diagnostic), and a connection
    # without that pragma would commit an ORPHAN observation.
    upper = dataclasses.replace(
        _reported_file(), file=FileKey(network=Network.ED2K, native_id=_HASH.upper())
    )
    with pytest.raises(PersistenceError, match="non-canonical eD2k hash"):
        observation_store.record_observation(
            FileObservation(reported_file=upper, observed_at=_T0, node_id=_NODE_ID)
        )
    assert _file_count(connection) == 0
    assert count_observations(connection) == 0


def test_outer_transaction_survives_record_observation_failure(
    *, observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    # Nested-transaction contract: the store's BEGIN fails ("cannot start a
    # transaction within a transaction") BEFORE the try → NO rollback is attempted,
    # the OUTER transaction and its pending rows SURVIVE.
    connection.execute("BEGIN")
    insert_file(connection, native_id=_HASH, size_bytes=1)
    with pytest.raises(PersistenceError, match="cannot start a transaction within a transaction"):
        observation_store.record_observation(
            FileObservation(reported_file=_reported_file(), observed_at=_T0, node_id=_NODE_ID)
        )
    assert connection.in_transaction  # the outer transaction is INTACT
    assert _file_count(connection) == 1
    connection.execute("ROLLBACK")
    assert _file_count(connection) == 0


def test_each_observation_stores_its_own_node_id(
    *, observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    observation_store.record_observation(
        FileObservation(reported_file=_reported_file(), observed_at=_T0, node_id=NodeId("n1"))
    )
    observation_store.record_observation(
        FileObservation(reported_file=_reported_file(), observed_at=_T0, node_id=NodeId("n2"))
    )
    assert rows(connection, sql="SELECT node_id FROM observation_variants ORDER BY variant_id") == [
        {"node_id": "n1"},
        {"node_id": "n2"},
    ]


def test_read_latest_observation_of_a_file_never_observed_is_none(
    *, observation_store: SqliteObservationStore, connection: sqlite3.Connection
) -> None:
    insert_file(connection, native_id=_HASH, size_bytes=1)
    assert observation_store.read_latest_observation(_KEY) is None
