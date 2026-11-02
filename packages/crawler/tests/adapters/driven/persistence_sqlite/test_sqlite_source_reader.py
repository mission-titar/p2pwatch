"""TDD tests for the catalog's source reader: sharing periods, sources, pages."""

import sqlite3
from collections.abc import Iterator, Sequence
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
from tests.support.adapters.driven.persistence_sqlite.catalog_seeds import seed
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


def _micros(at: datetime) -> int:
    return (at - _EPOCH) // timedelta(microseconds=1)


_WINDOW = PeriodWindow(since=_EPOCH, until=_at(100_000 * _S), gap=timedelta(seconds=90))

# (role, observed_at, session_received_bytes) of one source's points on file a, a variant per role.
_Points = Sequence[tuple[str, int, int]]


def _seed_points(db: Path, *, points: _Points) -> None:
    with closing(sqlite3.connect(db)) as connection, connection:
        insert_file(connection, native_id="a" * 32)
        insert_source(connection, user_hash=_USER)
        variants: dict[str, int] = {}
        for role, observed_at, counter in points:
            if role not in variants:
                variants[role] = insert_source_variant(
                    connection, native_id="a" * 32, user_hash=_USER, role=role
                )
            insert_source_point(
                connection,
                variant_id=variants[role],
                observed_at_micros=observed_at,
                session_received_bytes=counter,
            )


def _periods(db: Path, *, window: PeriodWindow = _WINDOW) -> list[tuple[str, int, int, int]]:
    """``(role, first_seen_at, last_seen_at, received_bytes)`` of file a's periods, in micros."""
    with ThreadReadConnections(db, open_reader=open_reader) as thread_read_connections:
        reader = SqliteSourceReader(thread_read_connections)
        periods = reader.read_sharing_periods(
            FileKey(network=Network.ED2K, native_id="a" * 32), window=window
        )
    return [
        (p.role.value, _micros(p.first_seen_at), _micros(p.last_seen_at), p.received_bytes)
        for p in periods
    ]


@pytest.mark.parametrize(
    ("seconds", "periods"),
    [
        ((0, 30, 60, 600), [(600, 600), (0, 60)]),
        ((0, 30, 120), [(0, 120)]),
    ],
    ids=["past-the-tolerance", "at-the-tolerance"],
)
def test_a_gap_past_the_tolerance_cuts_a_period(
    *, catalog_db: Path, seconds: tuple[int, ...], periods: list[tuple[int, int]]
) -> None:
    _seed_points(catalog_db, points=[("queued", at * _S, 0) for at in seconds])
    assert [(first // _S, last // _S) for _, first, last, _ in _periods(catalog_db)] == periods


def test_a_gap_a_microsecond_past_the_tolerance_cuts_a_period(catalog_db: Path) -> None:
    _seed_points(catalog_db, points=[("queued", 0, 0), ("queued", 90 * _S + 1, 0)])
    assert len(_periods(catalog_db)) == 2


def test_a_counter_that_drops_cuts_a_period(catalog_db: Path) -> None:
    _seed_points(catalog_db, points=[("sending", 0, 500), ("sending", 30 * _S, 100)])
    assert _periods(catalog_db) == [("sending", 30 * _S, 30 * _S, 0), ("sending", 0, 0, 0)]


@pytest.mark.parametrize(("role", "received"), [("sending", 500), ("queued", 0)])
def test_only_a_sending_period_shows_the_counters_growth(
    *, catalog_db: Path, role: str, received: int
) -> None:
    _seed_points(catalog_db, points=[(role, 0, 400), (role, 30 * _S, 650), (role, 60 * _S, 900)])
    assert _periods(catalog_db) == [(role, 0, 60 * _S, received)]


def test_a_change_of_variant_cuts_a_period_even_when_the_variant_comes_back(
    catalog_db: Path,
) -> None:
    _seed_points(
        catalog_db, points=[("queued", 0, 0), ("sending", 30 * _S, 0), ("queued", 60 * _S, 0)]
    )
    assert [role for role, *_ in _periods(catalog_db)] == ["queued", "sending", "queued"]


def test_a_sending_period_never_counts_the_bytes_of_a_standby_one_between(
    catalog_db: Path,
) -> None:
    # The standby counter grows with another file the source sends meanwhile.
    points = [("sending", 0, 100), ("standby", 30 * _S, 600), ("sending", 60 * _S, 700)]
    _seed_points(catalog_db, points=points)
    assert _periods(catalog_db) == [
        ("sending", 60 * _S, 60 * _S, 0),
        ("standby", 30 * _S, 30 * _S, 0),
        ("sending", 0, 0, 0),
    ]


def test_only_the_windows_points_are_read(catalog_db: Path) -> None:
    _seed_points(catalog_db, points=[("queued", at * _S, 0) for at in (0, 30, 60, 90)])
    window = PeriodWindow(since=_at(30 * _S), until=_at(90 * _S), gap=_WINDOW.gap)
    assert _periods(catalog_db, window=window) == [("queued", 30 * _S, 60 * _S, 0)]


def test_sharing_periods_join_each_identity_on_each_node_newest_first(catalog_db: Path) -> None:
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_file(connection, native_id="a" * 32)
        insert_file(connection, native_id="b" * 32)
        insert_source(connection, user_hash=_USER)
        queued = insert_source_variant(
            connection,
            native_id="a" * 32,
            user_hash=_USER,
            contact_point="198.51.100.7:4661",
            connectable=False,
        )
        elsewhere = insert_source_variant(
            connection, native_id="a" * 32, user_hash=_USER, node_id="n2"
        )
        unnamed = insert_source_variant(
            connection, native_id="a" * 32, user_hash=None, name=None, connectable=True
        )
        hashless = insert_source_variant(
            connection, native_id="a" * 32, user_hash=None, name="Teammate"
        )
        for variant, at in ((queued, 0), (elsewhere, 30), (queued, 60), (unnamed, 30)):
            insert_source_point(connection, variant_id=variant, observed_at_micros=at * _S)
        insert_source_point(connection, variant_id=hashless, observed_at_micros=45 * _S)
        insert_source_point(
            connection,
            variant_id=insert_source_variant(connection, native_id="b" * 32, user_hash=_USER),
            observed_at_micros=200 * _S,
        )
    a = FileKey(network=Network.ED2K, native_id="a" * 32)
    with ThreadReadConnections(catalog_db, open_reader=open_reader) as thread_read_connections:
        periods = SqliteSourceReader(thread_read_connections).read_sharing_periods(
            a, window=_WINDOW
        )
    key, queued_role = SourceKey(network=Network.ED2K, native_id=_USER), SourceRole.QUEUED
    at_30, at_45 = _at(30 * _S), _at(45 * _S)
    assert periods == (
        SharingPeriod(
            file=a,
            source=None,
            source_name="Teammate",
            role=queued_role,
            contact_point=None,
            connectable=None,
            first_seen_at=at_45,
            last_seen_at=at_45,
            received_bytes=0,
            node_id=NodeId("n1"),
        ),
        SharingPeriod(
            file=a,
            source=None,
            source_name=None,
            role=queued_role,
            contact_point=None,
            connectable=True,
            first_seen_at=at_30,
            last_seen_at=at_30,
            received_bytes=0,
            node_id=NodeId("n1"),
        ),
        SharingPeriod(
            file=a,
            source=key,
            source_name="AnimuseeFMR",
            role=queued_role,
            contact_point=None,
            connectable=None,
            first_seen_at=at_30,
            last_seen_at=at_30,
            received_bytes=0,
            node_id=NodeId("n2"),
        ),
        SharingPeriod(
            file=a,
            source=key,
            source_name="AnimuseeFMR",
            role=queued_role,
            contact_point="198.51.100.7:4661",
            connectable=False,
            first_seen_at=_at(0),
            last_seen_at=_at(60 * _S),
            received_bytes=0,
            node_id=NodeId("n1"),
        ),
    )


def test_sharing_periods_of_a_file_never_read_are_empty(catalog_db: Path) -> None:
    seed(catalog_db)
    with ThreadReadConnections(catalog_db, open_reader=open_reader) as thread_read_connections:
        reader = SqliteSourceReader(thread_read_connections)
        assert (
            reader.read_sharing_periods(
                FileKey(network=Network.ED2K, native_id="a" * 32), window=_WINDOW
            )
            == ()
        )


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
