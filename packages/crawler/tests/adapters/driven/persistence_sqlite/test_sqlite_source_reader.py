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
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.sharing_period import PeriodWindow, SharingPeriod
from p2pwatch.domain.source import SourceKey, SourceRole
from p2pwatch.domain.source_history import SourceHistory, SourceNameHistory, SourceNaming
from tests.contracts.application.ports.driven.source_reader_contract import SourceReaderContract
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    open_catalog,
    open_reader,
)
from tests.support.catalog_rows import (
    insert_file,
    insert_observation,
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

_OTHER = "9c0d" * 8


def _seed_sources(db: Path) -> None:
    """``_USER`` renamed on two files, then read without a name; ``_OTHER``, seen earlier."""
    with closing(sqlite3.connect(db)) as connection, connection:
        insert_file(connection, native_id="a" * 32)
        insert_file(connection, native_id="b" * 32)
        insert_source(connection, user_hash=_USER)
        insert_source(connection, user_hash=_OTHER)
        for native_id, user, name, role, seconds in (
            ("a", _USER, "Shinobu", "queued", (10, 20)),
            ("b", _USER, "AnimuseeFMR", "queued", (30, 40)),
            ("b", _USER, None, "sending", (50, 60)),
            ("a", _OTHER, "AnimuseeFMR", "queued", (0, 5)),
            ("a", None, "x", "queued", (70, 80)),
        ):
            variant = insert_source_variant(
                connection, native_id=native_id * 32, user_hash=user, name=name, role=role
            )
            for at in seconds:
                insert_source_point(connection, variant_id=variant, observed_at_micros=at)


_THIRD = "5a6b" * 8


def _seed_pages(db: Path) -> None:
    """``_seed_sources``, plus ``Keroro`` on ``_OTHER`` and ``_THIRD``, and a hash-less name."""
    _seed_sources(db)
    with closing(sqlite3.connect(db)) as connection, connection:
        insert_observation(connection, native_id="a" * 32, filename="keroro_062a.avi")
        insert_source(connection, user_hash=_THIRD)
        for user, at in ((_OTHER, 6), (_THIRD, 8)):
            variant = insert_source_variant(
                connection, native_id="a" * 32, user_hash=user, name="Keroro"
            )
            insert_source_point(connection, variant_id=variant, observed_at_micros=at)
        hashless = insert_source_variant(
            connection, native_id="b" * 32, user_hash=None, name="AnimuseeFMR", role="standby"
        )
        insert_source_point(connection, variant_id=hashless, observed_at_micros=95)


def _period(
    file: FileKey, *, source: SourceKey | None, source_name: str | None, first: int, last: int
) -> SharingPeriod:
    return SharingPeriod(
        file=file,
        source=source,
        source_name=source_name,
        role=SourceRole.QUEUED,
        contact_point=None,
        connectable=None,
        first_seen_at=_at(first),
        last_seen_at=_at(last),
        received_bytes=0,
        node_id=NodeId("n1"),
    )


def _source_history(
    db: Path, *, user: str, limit: int = _LIMIT, offset: int = 0, window: PeriodWindow = _WINDOW
) -> SourceHistory | None:
    with ThreadReadConnections(db, open_reader=open_reader) as thread_read_connections:
        reader = SqliteSourceReader(thread_read_connections)
        return reader.read_source_history(
            source_id(user), limit=limit, offset=offset, window=window
        )


def test_a_source_history_holds_its_names_its_periods_over_every_file_and_their_filenames(
    catalog_db: Path,
) -> None:
    _seed_pages(catalog_db)
    key, a, b = (
        SourceKey(network=Network.ED2K, native_id=_USER),
        FileKey(network=Network.ED2K, native_id="a" * 32),
        FileKey(network=Network.ED2K, native_id="b" * 32),
    )
    sending = SharingPeriod(
        file=b,
        source=key,
        source_name=None,
        role=SourceRole.SENDING,
        contact_point=None,
        connectable=None,
        first_seen_at=_at(50),
        last_seen_at=_at(60),
        received_bytes=0,
        node_id=NodeId("n1"),
    )
    assert _source_history(catalog_db, user=_USER) == SourceHistory(
        source=key,
        source_namings=(
            SourceNaming(
                source=key, source_name="AnimuseeFMR", latest_seen_at=_at(40), file_count=1
            ),
            SourceNaming(source=key, source_name="Shinobu", latest_seen_at=_at(20), file_count=1),
        ),
        sharing_periods=(
            sending,
            _period(b, source=key, source_name="AnimuseeFMR", first=30, last=40),
            _period(a, source=key, source_name="Shinobu", first=10, last=20),
        ),
        best_filename_by_file={a: "keroro_062a.avi"},
    )


def test_a_source_history_reads_at_most_its_limit_of_names_from_their_offset_and_every_period(
    catalog_db: Path,
) -> None:
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_file(connection, native_id="a" * 32)
        insert_source(connection, user_hash=_USER)
        for n in range(3):
            variant = insert_source_variant(
                connection, native_id="a" * 32, user_hash=_USER, name=f"name {n}"
            )
            insert_source_point(connection, variant_id=variant, observed_at_micros=n)
    source_history = _source_history(catalog_db, user=_USER, limit=2, offset=1)
    assert source_history is not None
    assert [naming.source_name for naming in source_history.source_namings] == [
        "name 1",
        "name 0",
    ]
    assert len(source_history.sharing_periods) == 3


def _source_name_history(
    db: Path,
    *,
    source_name: str,
    limit: int = _LIMIT,
    offset: int = 0,
    window: PeriodWindow = _WINDOW,
) -> SourceNameHistory | None:
    with ThreadReadConnections(db, open_reader=open_reader) as thread_read_connections:
        reader = SqliteSourceReader(thread_read_connections)
        return reader.read_source_name_history(
            source_name, limit=limit, offset=offset, window=window
        )


def test_a_source_name_history_holds_its_hashes_and_its_periods_without_one(
    catalog_db: Path,
) -> None:
    _seed_pages(catalog_db)
    user, other = (
        SourceKey(network=Network.ED2K, native_id=_USER),
        SourceKey(network=Network.ED2K, native_id=_OTHER),
    )
    b = FileKey(network=Network.ED2K, native_id="b" * 32)
    hashless = SharingPeriod(
        file=b,
        source=None,
        source_name="AnimuseeFMR",
        role=SourceRole.STANDBY,
        contact_point=None,
        connectable=None,
        first_seen_at=_at(95),
        last_seen_at=_at(95),
        received_bytes=0,
        node_id=NodeId("n1"),
    )
    assert _source_name_history(catalog_db, source_name="AnimuseeFMR") == SourceNameHistory(
        source_name="AnimuseeFMR",
        source_namings=(
            SourceNaming(
                source=user, source_name="AnimuseeFMR", latest_seen_at=_at(40), file_count=1
            ),
            SourceNaming(
                source=other, source_name="AnimuseeFMR", latest_seen_at=_at(5), file_count=1
            ),
        ),
        sharing_periods=(hashless,),
        best_filename_by_file={},
    )


def test_a_source_name_history_reads_at_most_its_limit_of_hashes_from_their_offset_and_every_period(
    catalog_db: Path,
) -> None:
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_file(connection, native_id="a" * 32)
        insert_observation(connection, native_id="a" * 32, filename="keroro_062a.avi")
        for n, role in enumerate(("standby", "queued", "sending")):
            insert_source(connection, user_hash=f"{n:032x}")
            insert_source_point(
                connection,
                variant_id=insert_source_variant(
                    connection, native_id="a" * 32, user_hash=f"{n:032x}"
                ),
                observed_at_micros=n,
            )
            insert_source_point(
                connection,
                variant_id=insert_source_variant(
                    connection, native_id="a" * 32, user_hash=None, role=role
                ),
                observed_at_micros=n,
            )
    source_name_history = _source_name_history(
        catalog_db, source_name="AnimuseeFMR", limit=2, offset=1
    )
    assert source_name_history is not None
    assert [naming.source.native_id for naming in source_name_history.source_namings] == [
        f"{1:032x}",
        f"{0:032x}",
    ]
    assert len(source_name_history.sharing_periods) == 3
    assert source_name_history.best_filename_by_file == {
        FileKey(network=Network.ED2K, native_id="a" * 32): "keroro_062a.avi"
    }


def test_the_history_of_a_source_never_recorded_is_none(catalog_db: Path) -> None:
    _seed_pages(catalog_db)
    assert _source_history(catalog_db, user="0" * 32) is None


def test_the_history_of_a_source_name_never_recorded_is_none(catalog_db: Path) -> None:
    _seed_pages(catalog_db)
    assert _source_name_history(catalog_db, source_name="nobody") is None


def test_the_pages_periods_are_read_in_the_window_only(catalog_db: Path) -> None:
    _seed_pages(catalog_db)
    window = PeriodWindow(since=_at(55), until=_at(1_000), gap=_WINDOW.gap)
    source = _source_history(catalog_db, user=_USER, window=window)
    name = _source_name_history(catalog_db, source_name="AnimuseeFMR", window=window)
    assert source is not None and name is not None
    assert [(p.first_seen_at, p.last_seen_at) for p in source.sharing_periods] == [
        (_at(60), _at(60))
    ]
    assert [(p.first_seen_at, p.last_seen_at) for p in name.sharing_periods] == [(_at(95), _at(95))]
