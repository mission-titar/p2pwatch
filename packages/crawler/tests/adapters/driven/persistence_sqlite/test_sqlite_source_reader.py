"""TDD tests for the catalog's source reader: sharing periods, sources, pages."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_source_point_store import (
    SqliteSourcePointStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_source_reader import SqliteSourceReader
from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import (
    ThreadReadConnections,
)
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.sharing_period import PeriodWindow
from tests.contracts.application.ports.driven.source_reader_contract import SourceReaderContract
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    open_catalog,
    open_reader,
)
from tests.support.catalog_rows import (
    insert_file,
    insert_source,
    insert_source_point,
    insert_source_variant,
    source_id,
)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_LIMIT = 50


@pytest.fixture
def connection(catalog_db: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(catalog_db)
    yield catalog
    catalog.close()


@pytest.fixture
def thread_read_connections(catalog_db: Path) -> Iterator[ThreadReadConnections]:
    with ThreadReadConnections(catalog_db, open_reader=open_reader) as thread_read_connections:
        yield thread_read_connections


class TestSqliteSourceReader(SourceReaderContract):
    @pytest.fixture
    def observation_writer(self, connection: sqlite3.Connection) -> SqliteObservationStore:
        return SqliteObservationStore(connection)

    @pytest.fixture
    def source_point_writer(self, connection: sqlite3.Connection) -> SqliteSourcePointStore:
        return SqliteSourcePointStore(connection)

    @pytest.fixture
    def reader(self, thread_read_connections: ThreadReadConnections) -> SqliteSourceReader:
        return SqliteSourceReader(thread_read_connections)


# ---------------------------------------------------------------------------
# Tests: a file's source history as periods (source points spec, D6)
# ---------------------------------------------------------------------------

_USER = "1f2e" * 8
_S = 1_000_000  # a second in microseconds


def _at(micros: int) -> datetime:
    return _EPOCH + timedelta(microseconds=micros)


_WINDOW = PeriodWindow(since=_EPOCH, until=_at(100_000 * _S), gap=timedelta(seconds=90))


def test_the_periods_started_by_one_reading_come_the_latest_recorded_variant_first(
    catalog_db: Path,
) -> None:
    # A tie the port leaves unstated (round-trip contracts spec, D6): no page cuts through it.
    roles = ("queued", "sending", "standby")
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_file(connection, native_id="a" * 32)
        insert_source(connection, user_hash=_USER)
        for role in roles:
            variant = insert_source_variant(
                connection, native_id="a" * 32, user_hash=_USER, role=role
            )
            insert_source_point(connection, variant_id=variant, observed_at_micros=0)
    with ThreadReadConnections(catalog_db, open_reader=open_reader) as thread_read_connections:
        periods = SqliteSourceReader(thread_read_connections).read_sharing_periods(
            FileKey(network=Network.ED2K, native_id="a" * 32), window=_WINDOW
        )
    assert [period.role for period in periods] == list(reversed(roles))


# ---------------------------------------------------------------------------
# Tests: the page of a source and the page of a name (stage 4 spec, D13)
# ---------------------------------------------------------------------------


def test_a_page_s_file_never_observed_has_no_best_filename(catalog_db: Path) -> None:
    # No Writer records a point on a file never observed (round-trip contracts spec, Appendix A).
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_file(connection, native_id="a" * 32)
        insert_source(connection, user_hash=_USER)
        variant = insert_source_variant(connection, native_id="a" * 32, user_hash=_USER)
        insert_source_point(connection, variant_id=variant, observed_at_micros=0)
    with ThreadReadConnections(catalog_db, open_reader=open_reader) as thread_read_connections:
        source_history = SqliteSourceReader(thread_read_connections).read_source_history(
            source_id(_USER), limit=_LIMIT, offset=0, window=_WINDOW
        )
    assert source_history is not None
    assert len(source_history.sharing_periods) == 1
    assert source_history.best_filename_by_file == {}
