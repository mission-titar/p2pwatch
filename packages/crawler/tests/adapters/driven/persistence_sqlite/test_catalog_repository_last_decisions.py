import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from catalog_matching.domain.engine import DecisionRecord, Explanation, MatchDecision
from p2pwatch.adapters.driven.persistence_sqlite.catalog_repository import SqliteCatalogRepository
from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.retraction import RETRACTED_TIER

_A = FileKey(Network.ED2K, "a" * 32)
_NODE = "11111111-2222-3333-4444-555555555555"
_T0 = datetime(2026, 6, 12, tzinfo=UTC)
_T1 = _T0 + timedelta(minutes=1)


def _reported_file(file: FileKey) -> ReportedFile:
    return ReportedFile(
        file=file,
        filename="Keroro.avi",
        size_bytes=100,
        source_count=1,
        keyword="keroro",
    )


def _decision(rule_name: str, tier: str, target_id: str = "062A") -> MatchDecision:
    return MatchDecision(
        target_id=target_id,
        rule_name=rule_name,
        tier=tier,
        explanation=Explanation(
            target_id=target_id, rules_fired=(rule_name,), tokens_matched=(), coverage_values=()
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


def test_last_decisions_is_empty_when_never_decided(
    repository: SqliteCatalogRepository,
) -> None:
    repository.record_observation(FileObservation(_reported_file(_A), _T0), _NODE)
    assert repository.read_latest_decisions(_A) == {}


def test_last_decisions_returns_the_latest_record_per_target(
    repository: SqliteCatalogRepository,
) -> None:
    repository.record_observation(FileObservation(_reported_file(_A), _T0), _NODE)
    repository.record_decision(_A, _decision("keroro_large", "catalog", "062A"), _T0, _NODE)
    repository.record_decision(
        _A, _decision("id_segment_exact", "download", "062A"), _T1, _NODE
    )  # newer
    repository.record_decision(_A, _decision("numero_nu", "notify", "062B"), _T0, _NODE)
    assert repository.read_latest_decisions(_A) == {
        "062A": DecisionRecord(target_id="062A", rule_name="id_segment_exact", tier="download"),
        "062B": DecisionRecord(target_id="062B", rule_name="numero_nu", tier="notify"),
    }


def test_last_decisions_includes_a_target_whose_latest_tier_is_retracted(
    repository: SqliteCatalogRepository,
) -> None:
    repository.record_observation(FileObservation(_reported_file(_A), _T0), _NODE)
    repository.record_decision(_A, _decision("id_segment_exact", "download", "062A"), _T0, _NODE)
    repository.record_decision(_A, _decision("", RETRACTED_TIER, "062A"), _T1, _NODE)
    assert repository.read_latest_decisions(_A) == {
        "062A": DecisionRecord(target_id="062A", rule_name="", tier=RETRACTED_TIER)
    }


def test_last_decisions_excludes_the_legacy_empty_sentinel(
    repository: SqliteCatalogRepository,
) -> None:
    repository.record_observation(FileObservation(_reported_file(_A), _T0), _NODE)
    repository.record_decision(_A, _decision("numero_nu", "notify", "062A"), _T0, _NODE)
    repository.record_decision(
        _A, _decision("", RETRACTED_TIER, ""), _T1, _NODE
    )  # legacy target_id=""
    assert repository.read_latest_decisions(_A) == {
        "062A": DecisionRecord(target_id="062A", rule_name="numero_nu", tier="notify")
    }


def test_last_decisions_for_unknown_hash_is_empty(
    repository: SqliteCatalogRepository,
) -> None:
    assert repository.read_latest_decisions(_A) == {}
