import dataclasses
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_catalog_scan_reader import (
    SqliteCatalogScanReader,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Keyword, NodeId
from p2pwatch.domain.observation import FileObservation, ReportedFile
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_catalog
from tests.support.catalog_rows import insert_file

_HASH = "31d6cfe0d16ae931b73c59d7e0c089c0"
_HASH_B = "b" * 32
_KEY = FileKey(Network.ED2K, _HASH)
_NODE_ID = NodeId("11111111-2222-3333-4444-555555555555")
_T0 = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)


def _reported_file(
    *,
    filename: str = "Keroro 062A.avi",
    size_bytes: int = 234567890,
    duration_seconds: int | None = None,
    bitrate_kbps: int | None = None,
) -> ReportedFile:
    return ReportedFile(
        file=_KEY,
        filename=filename,
        size_bytes=size_bytes,
        source_count=5,
        keyword=Keyword("keroro"),
        duration_seconds=duration_seconds,
        bitrate_kbps=bitrate_kbps,
    )


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(tmp_path / "catalog.db")
    yield catalog
    catalog.close()


@pytest.fixture
def observation_store(connection: sqlite3.Connection) -> SqliteObservationStore:
    return SqliteObservationStore(connection)


@pytest.fixture
def catalog_scan_reader(connection: sqlite3.Connection) -> SqliteCatalogScanReader:
    return SqliteCatalogScanReader(connection)


def test_iter_latest_observations_returns_the_latest_per_hash(
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
) -> None:
    # _HASH gets TWO observations a minute apart: only the LATEST must come back.
    # _HASH_B gets a single observation with media metadata present, by another node.
    newest = FileObservation(
        _reported_file(filename="new.avi", size_bytes=200), _T0 + timedelta(minutes=1), _NODE_ID
    )
    other = FileObservation(
        dataclasses.replace(
            _reported_file(
                filename="other.avi", size_bytes=300, duration_seconds=1234, bitrate_kbps=1500
            ),
            file=FileKey(Network.ED2K, _HASH_B),
        ),
        _T0,
        NodeId("n2"),
    )
    observation_store.record_observation(
        FileObservation(_reported_file(filename="old.avi", size_bytes=100), _T0, _NODE_ID)
    )
    observation_store.record_observation(newest)
    observation_store.record_observation(other)
    assert list(catalog_scan_reader.iter_latest_observations()) == [newest, other]


def test_iter_latest_observations_is_empty_with_an_empty_catalogue(
    catalog_scan_reader: SqliteCatalogScanReader,
) -> None:
    assert list(catalog_scan_reader.iter_latest_observations()) == []


def test_iter_latest_observations_breaks_an_observed_at_tie_on_the_highest_variant(
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
) -> None:
    # Both rows share observed_at, so the newer variant (higher variant_id) wins.
    observation_store.record_observation(
        FileObservation(_reported_file(filename="first.avi"), _T0, _NODE_ID)
    )
    observation_store.record_observation(
        FileObservation(_reported_file(filename="second.avi"), _T0, _NODE_ID)
    )
    filenames = [
        observation.reported_file.filename
        for observation in catalog_scan_reader.iter_latest_observations()
    ]
    assert filenames == ["second.avi"]


def test_read_file_count_counts_catalogued_hashes_not_observations(
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
) -> None:
    assert catalog_scan_reader.read_file_count() == 0
    observation_store.record_observation(FileObservation(_reported_file(), _T0, _NODE_ID))
    observation_store.record_observation(FileObservation(_reported_file(), _T0, _NODE_ID))
    observation_store.record_observation(
        FileObservation(
            dataclasses.replace(_reported_file(), file=FileKey(Network.ED2K, _HASH_B)),
            _T0,
            _NODE_ID,
        ),
    )
    assert catalog_scan_reader.read_file_count() == 2


def test_iter_latest_observations_skips_a_file_never_observed(
    catalog_scan_reader: SqliteCatalogScanReader, connection: sqlite3.Connection
) -> None:
    insert_file(connection, _HASH, 1)
    assert list(catalog_scan_reader.iter_latest_observations()) == []
