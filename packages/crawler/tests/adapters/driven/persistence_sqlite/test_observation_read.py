"""Every observation read, through one module (spec 2026-10-05)."""

import re
import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite import observation_read
from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import FileObservation, ReportedFile
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_catalog
from tests.support.catalog_rows import insert_file, insert_observation

_A, _B, _C = "a" * 32, "b" * 32, "c" * 32
_TIE = "2026-06-01T10:00:00.000000+00:00"
_YEAR_3000 = 32_503_680_000_000_000


def _key(native_id: str) -> FileKey:
    return FileKey(Network.ED2K, native_id)


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(tmp_path / "catalog.db")
    yield catalog
    catalog.close()


def _raw(
    connection: sqlite3.Connection,
    native_id: str,
    name: str,
    at: str,
    *,
    sources: int = 5,
    media: int | None = None,
    node_id: str = "n1",
) -> None:
    insert_observation(
        connection,
        native_id,
        name,
        observed_at=at,
        source_count=sources,
        duration_seconds=media,
        bitrate_kbps=None if media is None else 900,
        node_id=node_id,
    )


def _observation(
    name: str,
    at: str,
    *,
    media: int | None = None,
    native_id: str = _A,
    sources: int = 5,
    node_id: str = "n1",
) -> FileObservation:
    reported_file = ReportedFile(
        file=_key(native_id),
        filename=name,
        size_bytes=100,
        source_count=sources,
        keyword="keroro",
        duration_seconds=media,
        bitrate_kbps=None if media is None else 900,
    )
    return FileObservation(reported_file, datetime.fromisoformat(at), node_id)


def test_every_read_carries_the_node_of_its_observation(connection: sqlite3.Connection) -> None:
    insert_file(connection, _A)
    _raw(connection, _A, "keroro.avi", _TIE, node_id="n2")
    observation = _observation("keroro.avi", _TIE, node_id="n2")
    assert observation_read.latest_observation(connection, _key(_A)) == observation
    assert list(observation_read.iter_latest_observations(connection)) == [observation]
    assert observation_read.best_observation(connection, _key(_A)) == observation
    assert observation_read.observations_between(connection, _key(_A), 0, _YEAR_3000) == (
        observation,
    )


def test_latest_observation_is_the_latest_raw_observation(connection: sqlite3.Connection) -> None:
    insert_file(connection, _A)
    _raw(connection, _A, "old.avi", "2026-06-01T10:00:00.000000+00:00")
    _raw(connection, _A, "new.avi", "2026-06-02T10:00:00.000000+00:00", media=60)
    _raw(connection, _A, "older.avi", "2026-05-01T10:00:00.000000+00:00")
    latest = _observation("new.avi", "2026-06-02T10:00:00.000000+00:00", media=60)
    assert observation_read.latest_observation(connection, _key(_A)) == latest


def test_latest_observation_breaks_an_observed_at_tie_on_the_newest_variant_then_the_sources(
    connection: sqlite3.Connection,
) -> None:
    insert_file(connection, _A)
    _raw(connection, _A, "first.avi", _TIE, sources=9)
    _raw(connection, _A, "second.avi", _TIE, sources=1)
    _raw(connection, _A, "second.avi", _TIE, sources=4)
    latest = observation_read.latest_observation(connection, _key(_A))
    assert latest == _observation("second.avi", _TIE, sources=4)


def test_latest_observation_of_a_file_never_seen_or_unknown_is_none(
    connection: sqlite3.Connection,
) -> None:
    insert_file(connection, _A)
    assert observation_read.latest_observation(connection, _key(_A)) is None
    assert observation_read.latest_observation(connection, _key(_B)) is None


def test_iter_latest_observations_yields_one_per_seen_file_sorted_by_hash(
    connection: sqlite3.Connection,
) -> None:
    for native_id in (_C, _B, _A):
        insert_file(connection, native_id)
    _raw(connection, _C, "c.avi", "2026-05-01T10:00:00.000000+00:00")
    _raw(connection, _A, "old.avi", "2026-06-01T10:00:00.000000+00:00")
    _raw(connection, _A, "new.avi", "2026-06-02T10:00:00.000000+00:00")
    assert list(observation_read.iter_latest_observations(connection)) == [
        _observation("new.avi", "2026-06-02T10:00:00.000000+00:00"),
        _observation("c.avi", "2026-05-01T10:00:00.000000+00:00", native_id=_C),
    ]


def test_known_names_are_every_distinct_name_of_the_file_sorted(
    connection: sqlite3.Connection,
) -> None:
    insert_file(connection, _A)
    insert_file(connection, _B)
    _raw(connection, _A, "raw.avi", "2026-06-01T10:00:00.000000+00:00")
    _raw(connection, _A, "raw.avi", "2026-06-02T10:00:00.000000+00:00")
    _raw(connection, _A, "old [ES].avi", "2026-05-01T10:00:00.000000+00:00")
    _raw(connection, _B, "other.avi", "2026-05-01T10:00:00.000000+00:00")
    assert observation_read.known_filenames(connection, _key(_A)) == ("old [ES].avi", "raw.avi")
    assert observation_read.known_filenames(connection, _key(_C)) == ()


def test_best_observation_is_the_most_sourced(connection: sqlite3.Connection) -> None:
    insert_file(connection, _A)
    _raw(connection, _A, "clean.avi", "2026-06-01T10:00:00.000000+00:00", sources=8)
    _raw(connection, _A, "mojibake.avi", "2026-06-02T10:00:00.000000+00:00", sources=3)
    best = _observation("clean.avi", "2026-06-01T10:00:00.000000+00:00", sources=8)
    assert observation_read.best_observation(connection, _key(_A)) == best


def test_best_observation_takes_the_latest_seen_on_a_source_tie(
    connection: sqlite3.Connection,
) -> None:
    insert_file(connection, _A)
    _raw(connection, _A, "later.avi", "2026-06-02T10:00:00.000000+00:00")
    _raw(connection, _A, "earlier.avi", "2026-06-01T10:00:00.000000+00:00")
    best = _observation("later.avi", "2026-06-02T10:00:00.000000+00:00")
    assert observation_read.best_observation(connection, _key(_A)) == best


def test_best_observation_of_a_file_never_seen_is_none(connection: sqlite3.Connection) -> None:
    insert_file(connection, _A)
    assert observation_read.best_observation(connection, _key(_A)) is None


def test_observations_between_are_the_timeline_oldest_first(connection: sqlite3.Connection) -> None:
    insert_file(connection, _A)
    insert_file(connection, _B)
    _raw(connection, _A, "late.avi", "2026-06-02T10:00:00.000000+00:00")
    _raw(connection, _A, "early.avi", "2026-05-01T10:00:00.000000+00:00")
    _raw(connection, _A, "tie 1.avi", "2026-05-15T10:00:00.000000+00:00")
    _raw(connection, _A, "tie 2.avi", "2026-05-15T10:00:00.000000+00:00")
    _raw(connection, _B, "other.avi", "2026-05-20T10:00:00.000000+00:00")
    assert observation_read.observations_between(connection, _key(_A), 0, _YEAR_3000) == (
        _observation("early.avi", "2026-05-01T10:00:00.000000+00:00"),
        _observation("tie 1.avi", "2026-05-15T10:00:00.000000+00:00"),
        _observation("tie 2.avi", "2026-05-15T10:00:00.000000+00:00"),
        _observation("late.avi", "2026-06-02T10:00:00.000000+00:00"),
    )
    assert observation_read.observations_between(connection, _key(_C), 0, _YEAR_3000) == ()


def test_the_timeline_reads_its_interval_only(connection: sqlite3.Connection) -> None:
    insert_file(connection, _A)
    ats = [
        "2026-10-06T19:59:59.999999+00:00",
        "2026-10-06T20:00:00.000000+00:00",
        "2026-10-13T19:59:59.999999+00:00",
        "2026-10-13T20:00:00.000000+00:00",
    ]
    for n, at in enumerate(ats):
        _raw(connection, _A, f"{n}.avi", at)
    since = instant_to_micros(datetime.fromisoformat(ats[1]))
    until = instant_to_micros(datetime.fromisoformat(ats[3]))
    assert observation_read.observations_between(connection, _key(_A), since, until) == (
        _observation("1.avi", ats[1]),
        _observation("2.avi", ats[2]),
    )


@pytest.mark.parametrize(
    "sql",
    [
        observation_read.SELECT_LATEST_OBSERVATION,
        observation_read.SELECT_LATEST_OBSERVATIONS,
        observation_read._SELECT_OBSERVATIONS_BETWEEN,
        observation_read._SELECT_BEST_OBSERVATION,
    ],
    ids=["latest of one file", "latest of every file", "timeline", "best observation"],
)
def test_observation_reads_seek_a_variant_s_observations_by_primary_key(
    connection: sqlite3.Connection, sql: str
) -> None:
    # Asserts the PLAN, not a duration: a scan of observations is 11.6M rows on the node.
    plan = [
        str(row[3])
        for row in connection.execute("EXPLAIN QUERY PLAN " + sql, (_A,) * sql.count("?"))
    ]
    assert any(re.match(r"SEARCH o\w* USING PRIMARY KEY \(variant_id=\?", step) for step in plan), (
        plan
    )
    assert not any(step.startswith("SCAN o") for step in plan), plan


def test_the_timeline_seeks_its_interval_by_primary_key(connection: sqlite3.Connection) -> None:
    plan = [
        str(row[3])
        for row in connection.execute(
            "EXPLAIN QUERY PLAN " + observation_read._SELECT_OBSERVATIONS_BETWEEN, (_A, 0, 1)
        )
    ]
    assert (
        "SEARCH o USING PRIMARY KEY"
        " (variant_id=? AND observed_at_micros>? AND observed_at_micros<?)" in plan
    ), plan


def test_known_names_read_the_variants_alone(connection: sqlite3.Connection) -> None:
    tables: set[str] = set()

    def record(action: int, table: str | None, *_: str | None) -> int:
        if action == sqlite3.SQLITE_READ and table is not None:
            tables.add(table)
        return sqlite3.SQLITE_OK

    connection.set_authorizer(record)
    observation_read.known_filenames(connection, _key(_A))
    assert tables == {"observation_variants"}
