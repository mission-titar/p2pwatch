"""Every observation read, through one module (spec 2026-10-05)."""

import re
import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite import observation_read
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Keyword, NodeId
from p2pwatch.domain.observation import FileObservation, ReportedFile
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_catalog
from tests.support.catalog_rows import insert_file, insert_observation

_A, _B, _C = "a" * 32, "b" * 32, "c" * 32
_TIE = "2026-06-01T10:00:00.000000+00:00"
_YEAR_3000 = 32_503_680_000_000_000
_NODE_ID = NodeId("n1")


def _key(native_id: str) -> FileKey:
    return FileKey(network=Network.ED2K, native_id=native_id)


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(tmp_path / "catalog.db")
    yield catalog
    catalog.close()


def _raw(
    connection: sqlite3.Connection,
    *,
    native_id: str,
    name: str,
    at: str,
    sources: int = 5,
) -> None:
    insert_observation(
        connection, native_id=native_id, filename=name, observed_at=at, source_count=sources
    )


def _observation(
    name: str,
    *,
    at: str,
    native_id: str = _A,
    sources: int = 5,
) -> FileObservation:
    reported_file = ReportedFile(
        file=_key(native_id),
        filename=name,
        size_bytes=100,
        source_count=sources,
        keyword=Keyword("keroro"),
    )
    return FileObservation(
        reported_file=reported_file, observed_at=datetime.fromisoformat(at), node_id=_NODE_ID
    )


def test_latest_observation_breaks_an_observed_at_tie_on_the_newest_variant_then_the_sources(
    connection: sqlite3.Connection,
) -> None:
    insert_file(connection, native_id=_A)
    _raw(connection, native_id=_A, name="first.avi", at=_TIE, sources=9)
    _raw(connection, native_id=_A, name="second.avi", at=_TIE, sources=1)
    _raw(connection, native_id=_A, name="second.avi", at=_TIE, sources=4)
    latest = observation_read.latest_observation(connection, file=_key(_A))
    assert latest == _observation("second.avi", at=_TIE, sources=4)


def test_latest_observation_of_a_file_never_seen_or_unknown_is_none(
    connection: sqlite3.Connection,
) -> None:
    insert_file(connection, native_id=_A)
    assert observation_read.latest_observation(connection, file=_key(_A)) is None
    assert observation_read.latest_observation(connection, file=_key(_B)) is None


def test_iter_latest_observations_yields_one_per_seen_file_sorted_by_hash(
    connection: sqlite3.Connection,
) -> None:
    for native_id in (_C, _B, _A):
        insert_file(connection, native_id=native_id)
    _raw(connection, native_id=_C, name="c.avi", at="2026-05-01T10:00:00.000000+00:00")
    _raw(connection, native_id=_A, name="old.avi", at="2026-06-01T10:00:00.000000+00:00")
    _raw(connection, native_id=_A, name="new.avi", at="2026-06-02T10:00:00.000000+00:00")
    assert list(observation_read.iter_latest_observations(connection)) == [
        _observation("new.avi", at="2026-06-02T10:00:00.000000+00:00"),
        _observation("c.avi", at="2026-05-01T10:00:00.000000+00:00", native_id=_C),
    ]


def test_best_observation_of_a_file_never_seen_is_none(connection: sqlite3.Connection) -> None:
    insert_file(connection, native_id=_A)
    assert observation_read.best_observation(connection, file=_key(_A)) is None


def test_observations_between_are_the_timeline_oldest_first(connection: sqlite3.Connection) -> None:
    insert_file(connection, native_id=_A)
    insert_file(connection, native_id=_B)
    _raw(connection, native_id=_A, name="late.avi", at="2026-06-02T10:00:00.000000+00:00")
    _raw(connection, native_id=_A, name="early.avi", at="2026-05-01T10:00:00.000000+00:00")
    _raw(connection, native_id=_A, name="tie 1.avi", at="2026-05-15T10:00:00.000000+00:00")
    _raw(connection, native_id=_A, name="tie 2.avi", at="2026-05-15T10:00:00.000000+00:00")
    _raw(connection, native_id=_B, name="other.avi", at="2026-05-20T10:00:00.000000+00:00")
    assert observation_read.observations_between(
        connection, file=_key(_A), since=0, until=_YEAR_3000
    ) == (
        _observation("early.avi", at="2026-05-01T10:00:00.000000+00:00"),
        _observation("tie 1.avi", at="2026-05-15T10:00:00.000000+00:00"),
        _observation("tie 2.avi", at="2026-05-15T10:00:00.000000+00:00"),
        _observation("late.avi", at="2026-06-02T10:00:00.000000+00:00"),
    )
    assert (
        observation_read.observations_between(connection, file=_key(_C), since=0, until=_YEAR_3000)
        == ()
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
    *, connection: sqlite3.Connection, sql: str
) -> None:
    # Asserts the PLAN, not a duration: a scan of observations is 11.6M rows on the node.
    plan = [
        str(step["detail"])
        for step in rows(
            connection, sql="EXPLAIN QUERY PLAN " + sql, parameters=(_A,) * sql.count("?")
        )
    ]
    assert any(re.match(r"SEARCH o\w* USING PRIMARY KEY \(variant_id=\?", step) for step in plan), (
        plan
    )
    assert not any(step.startswith("SCAN o") for step in plan), plan


def test_the_timeline_seeks_its_interval_by_primary_key(connection: sqlite3.Connection) -> None:
    plan = [
        str(step["detail"])
        for step in rows(
            connection,
            sql="EXPLAIN QUERY PLAN " + observation_read._SELECT_OBSERVATIONS_BETWEEN,
            parameters=(_A, 0, 1),
        )
    ]
    assert (
        "SEARCH o USING PRIMARY KEY"
        " (variant_id=? AND observed_at_micros>? AND observed_at_micros<?)" in plan
    ), plan


def test_known_names_read_the_variants_alone(connection: sqlite3.Connection) -> None:
    tables: set[str] = set()

    def record(action: int, table: str | None, *_: str | None) -> int:  # noqa: PLR0917
        if action == sqlite3.SQLITE_READ and table is not None:
            tables.add(table)
        return sqlite3.SQLITE_OK

    connection.set_authorizer(record)
    observation_read.known_filenames(connection, file=_key(_A))
    assert tables == {"observation_variants"}
