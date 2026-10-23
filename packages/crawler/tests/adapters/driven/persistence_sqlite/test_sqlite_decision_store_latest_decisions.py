import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord, Explanation, MatchDecision
from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.retraction import RETRACTED_TIER
from tests.support.catalog_rows import insert_file

_A = FileKey(Network.ED2K, "a" * 32)
_NEVER_STORED = FileKey(Network.ED2K, "b" * 32)
_NODE = "11111111-2222-3333-4444-555555555555"
_T0 = datetime(2026, 6, 12, tzinfo=UTC)
_T1 = _T0 + timedelta(minutes=1)


def _decision(rule_name: str, tier: DecisionTier, target_id: str = "062A") -> MatchDecision:
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
def decision_store(connection: sqlite3.Connection) -> SqliteDecisionStore:
    insert_file(connection, _A.native_id)
    return SqliteDecisionStore(connection)


def test_latest_decisions_is_empty_when_never_decided(
    decision_store: SqliteDecisionStore,
) -> None:
    assert decision_store.read_latest_decisions(_A) == {}


def test_latest_decisions_returns_the_latest_record_per_target(
    decision_store: SqliteDecisionStore,
) -> None:
    decision_store.record_decision(
        _A, _decision("keroro_large", DecisionTier.CATALOG, "062A"), _T0, _NODE
    )
    decision_store.record_decision(
        _A, _decision("id_segment_exact", DecisionTier.DOWNLOAD, "062A"), _T1, _NODE
    )  # newer
    decision_store.record_decision(
        _A, _decision("numero_nu", DecisionTier.NOTIFY, "062B"), _T0, _NODE
    )
    assert decision_store.read_latest_decisions(_A) == {
        "062A": DecisionRecord(target_id="062A", rule_name="id_segment_exact", tier="download"),
        "062B": DecisionRecord(target_id="062B", rule_name="numero_nu", tier="notify"),
    }


def test_latest_decisions_includes_a_target_whose_latest_tier_is_retracted(
    decision_store: SqliteDecisionStore,
) -> None:
    decision_store.record_decision(
        _A, _decision("id_segment_exact", DecisionTier.DOWNLOAD, "062A"), _T0, _NODE
    )
    decision_store.record_retraction(_A, "062A", _T1, _NODE)
    assert decision_store.read_latest_decisions(_A) == {
        "062A": DecisionRecord(target_id="062A", rule_name="", tier=RETRACTED_TIER)
    }


def test_latest_decisions_excludes_the_legacy_empty_sentinel(
    decision_store: SqliteDecisionStore,
) -> None:
    decision_store.record_decision(
        _A, _decision("numero_nu", DecisionTier.NOTIFY, "062A"), _T0, _NODE
    )
    decision_store.record_retraction(_A, "", _T1, _NODE)  # legacy target_id=""
    assert decision_store.read_latest_decisions(_A) == {
        "062A": DecisionRecord(target_id="062A", rule_name="numero_nu", tier="notify")
    }


def test_latest_decisions_for_unknown_hash_is_empty(
    decision_store: SqliteDecisionStore,
) -> None:
    assert decision_store.read_latest_decisions(_NEVER_STORED) == {}
