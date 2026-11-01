import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.file_target_decision import DatedDecision, Retraction
from p2pwatch.domain.identifiers import NodeId
from tests.contracts.application.ports.driven.decision_store_contract import (
    DecisionStoreContract,
)
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_catalog
from tests.support.catalog_rows import insert_file

_HASH = "31d6cfe0d16ae931b73c59d7e0c089c0"
_KEY = FileKey(network=Network.ED2K, native_id=_HASH)
_NODE_ID = NodeId("11111111-2222-3333-4444-555555555555")
_T0 = datetime(2026, 6, 11, 12, 0, 0, 123456, tzinfo=UTC)
_TARGET_ID = TargetId("062A")


def _decision(
    file: FileKey, *, tier: DecisionTier = DecisionTier.DOWNLOAD, node_id: NodeId = _NODE_ID
) -> DatedDecision[DecisionRecord]:
    return DatedDecision(
        file=file,
        decision=DecisionRecord(target_id=_TARGET_ID, rule_name="exact_062a", tier=tier),
        decided_at=_T0,
        node_id=node_id,
    )


def _retraction(file: FileKey, *, node_id: NodeId = _NODE_ID) -> DatedDecision[Retraction]:
    return DatedDecision(
        file=file, decision=Retraction(target_id=TargetId("062A")), decided_at=_T0, node_id=node_id
    )


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(tmp_path / "catalog.db")
    yield catalog
    catalog.close()


@pytest.fixture
def decision_store(connection: sqlite3.Connection) -> SqliteDecisionStore:
    insert_file(connection, native_id=_HASH)
    return SqliteDecisionStore(connection)


class TestSqliteDecisionStore(DecisionStoreContract):
    @pytest.fixture
    def observation_writer(self, connection: sqlite3.Connection) -> SqliteObservationStore:
        return SqliteObservationStore(connection)

    @pytest.fixture
    def decision_store(self, connection: sqlite3.Connection) -> SqliteDecisionStore:
        # Without the module's raw `files` row: the contract seeds only through the Writers.
        return SqliteDecisionStore(connection)

    @pytest.fixture
    def writer(self, decision_store: SqliteDecisionStore) -> SqliteDecisionStore:
        return decision_store

    @pytest.fixture
    def reader(self, decision_store: SqliteDecisionStore) -> SqliteDecisionStore:
        return decision_store


def test_record_decision_round_trip(
    *, decision_store: SqliteDecisionStore, connection: sqlite3.Connection
) -> None:
    decision_store.record_decision(_decision(_KEY))
    assert rows(
        connection,
        sql="SELECT file_id, target_id, rule_name, tier,"
        " typeof(decided_at_micros) AS decided_at_type, decided_at_micros, node_id"
        " FROM match_decisions",
    ) == [
        {
            "file_id": _KEY.file_id,
            "target_id": "062A",
            "rule_name": "exact_062a",
            "tier": "download",
            "decided_at_type": "integer",
            "decided_at_micros": instant_to_micros(_T0),
            "node_id": _NODE_ID,
        }
    ]


def test_explanation_is_never_persisted(
    *, decision_store: SqliteDecisionStore, connection: sqlite3.Connection
) -> None:
    decision_store.record_decision(_decision(_KEY))
    columns = {
        column["name"] for column in rows(connection, sql="PRAGMA table_info(match_decisions)")
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
        decision_store.record_decision(_decision(FileKey(network=Network.ED2K, native_id="0" * 32)))


def test_record_decision_rejects_non_canonical_hash(
    *, decision_store: SqliteDecisionStore, connection: sqlite3.Connection
) -> None:
    # Python validation BEFORE any transaction: an uppercase hash is rejected
    # with a clear message, no row is written.
    with pytest.raises(PersistenceError, match="non-canonical eD2k hash"):
        decision_store.record_decision(
            _decision(FileKey(network=Network.ED2K, native_id=_HASH.upper()))
        )
    assert rows(connection, sql="SELECT count(*) AS decision_count FROM match_decisions") == [
        {"decision_count": 0}
    ]


def test_record_retraction_round_trip(
    *, decision_store: SqliteDecisionStore, connection: sqlite3.Connection
) -> None:
    decision_store.record_decision(_retraction(_KEY))
    assert rows(
        connection,
        sql="SELECT file_id, target_id, rule_name, tier, decided_at_micros, node_id"
        " FROM match_decisions",
    ) == [
        {
            "file_id": _KEY.file_id,
            "target_id": "062A",
            "rule_name": "",
            "tier": "retracted",
            "decided_at_micros": instant_to_micros(_T0),
            "node_id": _NODE_ID,
        }
    ]
    assert decision_store.read_latest_decisions(_KEY) == {
        TargetId("062A"): Retraction(target_id=TargetId("062A"))
    }


def test_each_decision_stores_its_own_node_id(
    *, decision_store: SqliteDecisionStore, connection: sqlite3.Connection
) -> None:
    decision_store.record_decision(_decision(_KEY, node_id=NodeId("n2")))
    decision_store.record_decision(_retraction(_KEY, node_id=NodeId("n3")))
    assert rows(connection, sql="SELECT node_id FROM match_decisions ORDER BY id") == [
        {"node_id": "n2"},
        {"node_id": "n3"},
    ]


def test_record_retraction_row_is_append_only(
    *, decision_store: SqliteDecisionStore, connection: sqlite3.Connection
) -> None:
    decision_store.record_decision(_retraction(_KEY))
    with pytest.raises(sqlite3.IntegrityError, match="match_decisions is append-only"):
        connection.execute("UPDATE match_decisions SET tier = 'catalog'")
    with pytest.raises(sqlite3.IntegrityError, match="match_decisions is append-only"):
        connection.execute("DELETE FROM match_decisions")
    # The retracted row SURVIVED both attempts, untouched.
    assert decision_store.read_latest_decisions(_KEY) == {
        TargetId("062A"): Retraction(target_id=TargetId("062A"))
    }


def test_of_two_decisions_of_the_same_instant_the_last_recorded_is_the_latest(
    decision_store: SqliteDecisionStore,
) -> None:
    decision_store.record_decision(_decision(_KEY, tier=DecisionTier.DOWNLOAD))
    decision_store.record_decision(_decision(_KEY, tier=DecisionTier.CATALOG))
    assert decision_store.read_latest_decisions(_KEY) == {
        _TARGET_ID: DecisionRecord(
            target_id=_TARGET_ID, rule_name="exact_062a", tier=DecisionTier.CATALOG
        )
    }
    assert decision_store.read_download_candidates() == ()
