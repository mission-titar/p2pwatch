import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.catalog_repository import SqliteCatalogRepository
from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import FileObservation, ReportedFile

_A = FileKey(Network.ED2K, "a" * 32)
_B = FileKey(Network.ED2K, "b" * 32)
_NODE = "11111111-2222-3333-4444-555555555555"
_T0 = datetime(2026, 6, 12, tzinfo=UTC)
_T1 = _T0 + timedelta(minutes=1)


def _reported_file(file: FileKey, *, name: str = "Keroro.avi", size: int = 100) -> ReportedFile:
    return ReportedFile(
        file=file,
        filename=name,
        size_bytes=size,
        source_count=1,
        keyword="keroro",
    )


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(tmp_path / "catalog.db")
    yield catalog
    catalog.close()


@pytest.fixture
def repository(connection: sqlite3.Connection) -> SqliteCatalogRepository:
    return SqliteCatalogRepository(connection)


def test_last_observation_returns_the_observation_whole(
    repository: SqliteCatalogRepository,
) -> None:
    observation = FileObservation(_reported_file(_A, name="Keroro 062A.avi", size=4242), _T0)
    repository.record_observation(observation, _NODE)
    assert repository.read_latest_observation(_A) == observation


def test_last_observation_returns_the_most_recent(
    repository: SqliteCatalogRepository,
) -> None:
    repository.record_observation(
        FileObservation(_reported_file(_A, name="old.avi", size=1), _T0), _NODE
    )
    newest = FileObservation(_reported_file(_A, name="new.avi", size=2), _T1)
    repository.record_observation(newest, _NODE)
    assert repository.read_latest_observation(_A) == newest


def test_last_observation_unknown_hash_is_none(repository: SqliteCatalogRepository) -> None:
    assert repository.read_latest_observation(_A) is None


def test_best_observation_is_the_observation_of_the_clean_name(
    repository: SqliteCatalogRepository,
) -> None:
    observation = FileObservation(_reported_file(_A, name="clean.avi", size=7), _T0)
    repository.record_observation(observation, _NODE)
    assert repository.read_best_observation(_A) == observation
    assert repository.read_best_observation(_B) is None


def test_known_filenames_are_the_distinct_sorted_names_of_that_hash_only(
    repository: SqliteCatalogRepository,
) -> None:
    repository.record_observation(
        FileObservation(_reported_file(_A, name="b.avi", size=1), _T0), _NODE
    )
    repository.record_observation(
        FileObservation(_reported_file(_A, name="a.avi", size=1), _T0), _NODE
    )
    repository.record_observation(
        FileObservation(_reported_file(_A, name="b.avi", size=1), _T0), _NODE
    )
    repository.record_observation(
        FileObservation(_reported_file(_B, name="other.avi", size=1), _T0), _NODE
    )
    assert repository.read_known_filenames(_A) == ("a.avi", "b.avi")


def test_known_filenames_of_an_unknown_hash_is_empty(repository: SqliteCatalogRepository) -> None:
    assert repository.read_known_filenames(_A) == ()
