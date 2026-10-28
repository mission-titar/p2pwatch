import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.domain.download.candidate import DownloadCandidate
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.file_target_decision import DatedDecision, Retraction
from p2pwatch.domain.identifiers import NodeId
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_catalog
from tests.support.catalog_rows import insert_file

_HASH = "31d6cfe0d16ae931b73c59d7e0c089c0"
_KEY = FileKey(Network.ED2K, _HASH)
_A = FileKey(Network.ED2K, "a" * 32)
_B = FileKey(Network.ED2K, "b" * 32)
_NODE_ID = NodeId("11111111-2222-3333-4444-555555555555")
_T0 = datetime(2026, 6, 11, 12, 0, 0, 123456, tzinfo=UTC)
_T1 = _T0 + timedelta(minutes=1)
_TARGET_ID = TargetId("062A")


def _decision(
    file: FileKey,
    tier: DecisionTier = DecisionTier.DOWNLOAD,
    target_id: TargetId = _TARGET_ID,
    decided_at: datetime = _T0,
    node_id: NodeId = _NODE_ID,
) -> DatedDecision[DecisionRecord]:
    return DatedDecision(file, DecisionRecord(target_id, "exact_062a", tier), decided_at, node_id)


def _retraction(file: FileKey, node_id: NodeId = _NODE_ID) -> DatedDecision[Retraction]:
    return DatedDecision(file, Retraction(TargetId("062A")), _T0, node_id)


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(tmp_path / "catalog.db")
    for file in (_KEY, _A, _B):
        insert_file(catalog, file.native_id)
    yield catalog
    catalog.close()


@pytest.fixture
def decision_store(connection: sqlite3.Connection) -> SqliteDecisionStore:
    return SqliteDecisionStore(connection)


def test_record_decision_round_trip(
    decision_store: SqliteDecisionStore, connection: sqlite3.Connection
) -> None:
    decision_store.record_decision(_decision(_KEY))
    row = connection.execute(
        "SELECT file_id, target_id, rule_name, tier, typeof(decided_at_micros), decided_at_micros,"
        " node_id FROM match_decisions"
    ).fetchone()
    assert row == (
        _KEY.file_id,
        "062A",
        "exact_062a",
        "download",
        "integer",
        instant_to_micros(_T0),
        _NODE_ID,
    )


def test_explanation_is_never_persisted(
    decision_store: SqliteDecisionStore, connection: sqlite3.Connection
) -> None:
    decision_store.record_decision(_decision(_KEY))
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(match_decisions)").fetchall()
    }
    assert columns == {
        "id",
        "file_id",
        "target_id",
        "rule_name",
        "tier",
        "decided_at_micros",
        "node_id",
    }


def test_record_decision_for_unknown_file_raises_persistence_error(
    decision_store: SqliteDecisionStore,
) -> None:
    # FK violated (file never observed): sqlite3.IntegrityError WRAPPED, never bare.
    with pytest.raises(PersistenceError, match="FOREIGN KEY"):
        decision_store.record_decision(_decision(FileKey(Network.ED2K, "0" * 32)))


def test_record_decision_rejects_non_canonical_hash(
    decision_store: SqliteDecisionStore, connection: sqlite3.Connection
) -> None:
    # Python validation BEFORE any transaction: an uppercase hash is rejected
    # with a clear message, no row is written.
    with pytest.raises(PersistenceError, match="non-canonical eD2k hash"):
        decision_store.record_decision(_decision(FileKey(Network.ED2K, _HASH.upper())))
    assert connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 0


def test_record_retraction_round_trip(
    decision_store: SqliteDecisionStore, connection: sqlite3.Connection
) -> None:
    decision_store.record_decision(_retraction(_KEY))
    row = connection.execute(
        "SELECT file_id, target_id, rule_name, tier, decided_at_micros, node_id"
        " FROM match_decisions"
    ).fetchone()
    assert row == (_KEY.file_id, "062A", "", "retracted", instant_to_micros(_T0), _NODE_ID)
    assert decision_store.read_latest_decisions(_KEY) == {
        TargetId("062A"): Retraction(TargetId("062A"))
    }


def test_each_decision_stores_its_own_node_id(
    decision_store: SqliteDecisionStore, connection: sqlite3.Connection
) -> None:
    decision_store.record_decision(_decision(_KEY, node_id=NodeId("n2")))
    decision_store.record_decision(_retraction(_KEY, node_id=NodeId("n3")))
    decisions = connection.execute("SELECT node_id FROM match_decisions ORDER BY id")
    assert decisions.fetchall() == [("n2",), ("n3",)]


def test_record_retraction_row_is_append_only(
    decision_store: SqliteDecisionStore, connection: sqlite3.Connection
) -> None:
    decision_store.record_decision(_retraction(_KEY))
    with pytest.raises(sqlite3.IntegrityError, match="match_decisions is append-only"):
        connection.execute("UPDATE match_decisions SET tier = 'catalog'")
    with pytest.raises(sqlite3.IntegrityError, match="match_decisions is append-only"):
        connection.execute("DELETE FROM match_decisions")
    # The retracted row SURVIVED both attempts, untouched.
    assert decision_store.read_latest_decisions(_KEY) == {
        TargetId("062A"): Retraction(TargetId("062A"))
    }


def test_download_candidates_include_a_file_whose_latest_verdict_is_download(
    decision_store: SqliteDecisionStore,
) -> None:
    decision_store.record_decision(_decision(_A, DecisionTier.CATALOG))
    # newer = download
    decision_store.record_decision(_decision(_A, DecisionTier.DOWNLOAD, decided_at=_T1))
    assert decision_store.read_download_candidates() == (
        DownloadCandidate(file=_A, target_id=TargetId("062A")),
    )


def test_download_candidates_include_a_single_download_only_decision(
    decision_store: SqliteDecisionStore,
) -> None:
    decision_store.record_decision(_decision(_A, DecisionTier.DOWNLOAD))
    assert decision_store.read_download_candidates() == (
        DownloadCandidate(file=_A, target_id=TargetId("062A")),
    )


def test_download_candidates_exclude_a_file_whose_latest_verdict_is_not_download(
    decision_store: SqliteDecisionStore,
) -> None:
    decision_store.record_decision(_decision(_B, DecisionTier.DOWNLOAD))
    # newer = catalog
    decision_store.record_decision(_decision(_B, DecisionTier.CATALOG, decided_at=_T1))
    assert decision_store.read_download_candidates() == ()


def test_download_candidates_isolate_each_file(decision_store: SqliteDecisionStore) -> None:
    # The PARTITION BY file_id window isolates _A, ending in download, from _B, in catalog.
    decision_store.record_decision(_decision(_A, DecisionTier.CATALOG))
    decision_store.record_decision(_decision(_A, DecisionTier.DOWNLOAD, decided_at=_T1))
    decision_store.record_decision(_decision(_B, DecisionTier.DOWNLOAD))
    decision_store.record_decision(_decision(_B, DecisionTier.CATALOG, decided_at=_T1))
    assert decision_store.read_download_candidates() == (
        DownloadCandidate(file=_A, target_id=TargetId("062A")),
    )


def test_download_candidates_are_empty_with_no_decisions(
    decision_store: SqliteDecisionStore,
) -> None:
    assert decision_store.read_download_candidates() == ()


def test_download_candidates_hold_both_segments_of_one_file(
    decision_store: SqliteDecisionStore,
) -> None:
    # spec §6: a whole-episode file both segments in download must NOT lose a candidate.
    decision_store.record_decision(_decision(_A, DecisionTier.DOWNLOAD, TargetId("062A")))
    decision_store.record_decision(_decision(_A, DecisionTier.DOWNLOAD, TargetId("062B")))
    assert decision_store.read_download_candidates() == (
        DownloadCandidate(file=_A, target_id=TargetId("062A")),
        DownloadCandidate(file=_A, target_id=TargetId("062B")),
    )


def test_download_candidates_isolate_each_target_within_one_file(
    decision_store: SqliteDecisionStore,
) -> None:
    # same file, two targets: 062A latest=download, 062B latest=catalog → only 062A.
    decision_store.record_decision(_decision(_A, DecisionTier.DOWNLOAD, TargetId("062A")))
    decision_store.record_decision(_decision(_A, DecisionTier.CATALOG, TargetId("062B")))
    assert decision_store.read_download_candidates() == (
        DownloadCandidate(file=_A, target_id=TargetId("062A")),
    )
