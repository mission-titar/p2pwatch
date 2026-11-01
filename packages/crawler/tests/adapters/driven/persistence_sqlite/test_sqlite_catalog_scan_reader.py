import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
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
from tests.contracts.application.ports.driven.catalog_scan_reader_contract import (
    CatalogScanReaderContract,
)
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_catalog
from tests.support.catalog_rows import insert_file

_HASH = "31d6cfe0d16ae931b73c59d7e0c089c0"
_KEY = FileKey(network=Network.ED2K, native_id=_HASH)
_NODE_ID = NodeId("11111111-2222-3333-4444-555555555555")
_T0 = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)


def _reported_file(*, filename: str) -> ReportedFile:
    return ReportedFile(
        file=_KEY,
        filename=filename,
        size_bytes=234567890,
        source_count=5,
        keyword=Keyword("keroro"),
        duration_seconds=None,
        bitrate_kbps=None,
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


class TestSqliteCatalogScanReader(CatalogScanReaderContract):
    @pytest.fixture
    def observation_writer(
        self, observation_store: SqliteObservationStore
    ) -> SqliteObservationStore:
        return observation_store

    @pytest.fixture
    def reader(self, catalog_scan_reader: SqliteCatalogScanReader) -> SqliteCatalogScanReader:
        return catalog_scan_reader


def test_iter_latest_observations_breaks_an_observed_at_tie_on_the_highest_variant(
    *,
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
) -> None:
    # Both rows share observed_at, so the newer variant (higher variant_id) wins.
    observation_store.record_observation(
        FileObservation(
            reported_file=_reported_file(filename="first.avi"), observed_at=_T0, node_id=_NODE_ID
        )
    )
    observation_store.record_observation(
        FileObservation(
            reported_file=_reported_file(filename="second.avi"), observed_at=_T0, node_id=_NODE_ID
        )
    )
    filenames = [
        observation.reported_file.filename
        for observation in catalog_scan_reader.iter_latest_observations()
    ]
    assert filenames == ["second.avi"]


def test_iter_latest_observations_skips_a_file_never_observed(
    *, catalog_scan_reader: SqliteCatalogScanReader, connection: sqlite3.Connection
) -> None:
    insert_file(connection, native_id=_HASH, size_bytes=1)
    assert list(catalog_scan_reader.iter_latest_observations()) == []
