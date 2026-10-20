import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from catalog_matching.domain.engine import Explanation, MatchDecision
from p2pwatch.adapters.driven.persistence_sqlite.catalog_repository import SqliteCatalogRepository
from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.ports.driven.catalog import DownloadCandidate

_A = FileKey(Network.ED2K, "a" * 32)
_B = FileKey(Network.ED2K, "b" * 32)
_C = FileKey(Network.ED2K, "c" * 32)
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


def _decision(tier: str, target_id: str = "062A") -> MatchDecision:
    return MatchDecision(
        target_id=target_id,
        rule_name="r",
        tier=tier,
        explanation=Explanation(
            target_id=target_id, rules_fired=("r",), tokens_matched=(), coverage_values=()
        ),
    )


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(tmp_path / "catalog.db")
    yield catalog
    catalog.close()


@pytest.fixture
def repository(connection: sqlite3.Connection) -> SqliteCatalogRepository:
    return SqliteCatalogRepository(connection)


def test_download_decisions_includes_hash_whose_latest_verdict_is_download(
    repository: SqliteCatalogRepository,
) -> None:
    repository.record_observation(FileObservation(_reported_file(_A), _T0), _NODE)
    repository.record_decision(_A, _decision("catalog"), _T0, _NODE)
    repository.record_decision(_A, _decision("download"), _T1, _NODE)  # more recent = download
    assert repository.read_download_candidates() == (DownloadCandidate(file=_A, target_id="062A"),)


def test_download_decisions_includes_a_single_download_only_decision(
    repository: SqliteCatalogRepository,
) -> None:
    repository.record_observation(FileObservation(_reported_file(_A), _T0), _NODE)
    repository.record_decision(
        _A, _decision("download"), _T0, _NODE
    )  # a single decision, = download
    assert repository.read_download_candidates() == (DownloadCandidate(file=_A, target_id="062A"),)


def test_download_decisions_excludes_hash_whose_latest_verdict_is_not_download(
    repository: SqliteCatalogRepository,
) -> None:
    repository.record_observation(FileObservation(_reported_file(_B), _T0), _NODE)
    repository.record_decision(_B, _decision("download"), _T0, _NODE)
    repository.record_decision(_B, _decision("catalog"), _T1, _NODE)  # more recent = catalog
    assert repository.read_download_candidates() == ()


def test_download_decisions_isolates_per_hash(
    repository: SqliteCatalogRepository,
) -> None:
    # two distinct hashes in the same query: _A ends in download, _B ends in catalog.
    # The PARTITION BY file_id window must isolate them → only _A is returned.
    repository.record_observation(FileObservation(_reported_file(_A), _T0), _NODE)
    repository.record_observation(FileObservation(_reported_file(_B), _T0), _NODE)
    repository.record_decision(_A, _decision("catalog"), _T0, _NODE)
    repository.record_decision(_A, _decision("download"), _T1, _NODE)  # _A latest = download
    repository.record_decision(_B, _decision("download"), _T0, _NODE)
    repository.record_decision(_B, _decision("catalog"), _T1, _NODE)  # _B latest = catalog
    assert repository.read_download_candidates() == (DownloadCandidate(file=_A, target_id="062A"),)


def test_download_decisions_is_empty_with_no_decisions(
    repository: SqliteCatalogRepository,
) -> None:
    repository.record_observation(FileObservation(_reported_file(_C), _T0), _NODE)
    assert repository.read_download_candidates() == ()


def test_download_decisions_returns_both_segments_of_one_hash(
    repository: SqliteCatalogRepository,
) -> None:
    # spec §6: a whole-episode file both segments in download must NOT lose a candidate.
    repository.record_observation(FileObservation(_reported_file(_A), _T0), _NODE)
    repository.record_decision(_A, _decision("download", "062A"), _T0, _NODE)
    repository.record_decision(_A, _decision("download", "062B"), _T0, _NODE)
    assert repository.read_download_candidates() == (
        DownloadCandidate(file=_A, target_id="062A"),
        DownloadCandidate(file=_A, target_id="062B"),
    )


def test_download_decisions_isolates_per_target_within_one_hash(
    repository: SqliteCatalogRepository,
) -> None:
    # same hash, two targets: 062A latest=download, 062B latest=catalog → only 062A.
    repository.record_observation(FileObservation(_reported_file(_A), _T0), _NODE)
    repository.record_decision(_A, _decision("download", "062A"), _T0, _NODE)
    repository.record_decision(_A, _decision("catalog", "062B"), _T0, _NODE)
    assert repository.read_download_candidates() == (DownloadCandidate(file=_A, target_id="062A"),)


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
