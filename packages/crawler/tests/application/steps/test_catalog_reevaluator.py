"""A changed policy re-judges every catalogued file at the start, then stores its fingerprint.

Real engine and SQLite stores, the real file judge and dispatch step over fakes. Each file under
test is seeded through ``observation_store.record_observation`` so the scan reaches it.
"""

import sqlite3
from datetime import timedelta

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord, MatchingEngine, to_record
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_catalog_scan_reader import (
    SqliteCatalogScanReader,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.application.steps.catalog_reevaluator import CatalogReevaluator
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.file_target_decision import DatedDecision, Retraction
from p2pwatch.domain.identifiers import Keyword, NodeId
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.store_error import StoreError
from p2pwatch.domain.wake_subject import WakeSubject
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_policy_fingerprint_store import FakePolicyFingerprintStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.fakes.adapters.driven.fake_wall_clock import FakeWallClock
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes
from tests.support.catalog_rows import decision_node_ids, decision_tiers

_NODE_ID = NodeId("n1")
_FINGERPRINT = "policy-2"
_HASH_DL = "31d6cfe0d16ae931b73c59d7e0c089c0"
_HASH_CAT = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_HASH_MULTI = "dddddddddddddddddddddddddddddddd"
_DL_NAME = "Keroro N°062A Les demoiselles cambrioleuses.avi"
_CAT_NAME = "keroro something.avi"
_MULTI_NAME = "Keroro 062 teletoon.avi"  # → 062A + 062B download (post-fan-out)


class _Reevaluation:
    """A ``CatalogReevaluator`` over the real stores, its outputs landing in fakes."""

    def __init__(
        self,
        observation_store: SqliteObservationStore,
        decision_store: SqliteDecisionStore,
        catalog_scan_reader: SqliteCatalogScanReader,
        engine: MatchingEngine,
        wall_clock: FakeWallClock,
        *,
        stored_fingerprint: str | None = "policy-1",
        progress_every_files: int = 200,
    ) -> None:
        self.fingerprints = FakePolicyFingerprintStore(stored_fingerprint=stored_fingerprint)
        self.observability = ObservabilityOverFakes()
        self.waker = FakeWaker()
        self.logger = FakeLogger()
        self.catalog_reevaluator = CatalogReevaluator(
            policy_fingerprint=_FINGERPRINT,
            policy_fingerprint_reader=self.fingerprints,
            policy_fingerprint_writer=self.fingerprints,
            file_judge=FileJudge(
                observation_reader=observation_store,
                decision_writer=decision_store,
                decision_reader=decision_store,
                engine=engine,
                waker=self.waker,
                observability_dispatcher=self.observability.dispatcher,
                wall_clock=wall_clock,
            ),
            catalog_scan_reader=catalog_scan_reader,
            progress_every_files=progress_every_files,
            logger=self.logger,
        )

    async def run(self) -> None:
        await self.catalog_reevaluator.reevaluate_if_policy_changed(_NODE_ID)


def _reported_file(native_id: str, filename: str) -> ReportedFile:
    return ReportedFile(
        file=FileKey(Network.ED2K, native_id),
        filename=filename,
        size_bytes=234_000_000,
        source_count=3,
        keyword=Keyword("keroro"),
    )


@pytest.mark.asyncio
async def test_an_unchanged_policy_skips_the_re_evaluation(
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_DL, _DL_NAME), wall_clock.now(), _NODE_ID)
    )
    reevaluation = _Reevaluation(
        observation_store,
        decision_store,
        catalog_scan_reader,
        engine,
        wall_clock,
        stored_fingerprint=_FINGERPRINT,
    )

    await reevaluation.run()

    assert reevaluation.logger.lines == [
        LoggedLine("info", "policy unchanged: catalogue re-evaluation skipped")
    ]
    assert decision_tiers(catalog_connection) == []
    assert reevaluation.fingerprints.set_calls == []


@pytest.mark.asyncio
async def test_without_a_stored_fingerprint_the_catalog_is_re_evaluated_then_it_is_stored(
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    reevaluation = _Reevaluation(
        observation_store,
        decision_store,
        catalog_scan_reader,
        engine,
        wall_clock,
        stored_fingerprint=None,
    )

    await reevaluation.run()

    assert reevaluation.logger.lines == [
        LoggedLine("info", "catalogue re-evaluated: 0 files, 0 rows written")
    ]
    assert reevaluation.fingerprints.set_calls == [_FINGERPRINT]
    assert reevaluation.observability.logger.lines == []
    assert reevaluation.waker.woken_subjects == []


@pytest.mark.asyncio
async def test_a_failing_scan_propagates_and_leaves_the_fingerprint_unstored(
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    reevaluation = _Reevaluation(
        observation_store, decision_store, catalog_scan_reader, engine, wall_clock
    )
    catalog_connection.close()  # the next start sees the old fingerprint and retries the pass

    with pytest.raises(StoreError, match="closed database"):
        await reevaluation.run()

    assert reevaluation.fingerprints.set_calls == []


@pytest.mark.asyncio
async def test_two_changed_rows_are_all_evaluated_and_written(
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # Never decided: both will change.
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_DL, _DL_NAME), wall_clock.now(), _NODE_ID)
    )
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _CAT_NAME), wall_clock.now(), _NODE_ID)
    )
    reevaluation = _Reevaluation(
        observation_store, decision_store, catalog_scan_reader, engine, wall_clock
    )

    await reevaluation.run()

    assert reevaluation.logger.lines == [
        LoggedLine("info", "catalogue re-evaluated: 2 files, 2 rows written")
    ]
    assert reevaluation.fingerprints.set_calls == [_FINGERPRINT]
    tiers = dict(decision_tiers(catalog_connection))
    assert tiers == {_HASH_DL: "download", _HASH_CAT: "catalog"}
    assert decision_node_ids(catalog_connection) == {_NODE_ID}
    decided_at_micros = catalog_connection.execute(
        "SELECT DISTINCT decided_at_micros FROM match_decisions"
    )
    assert decided_at_micros.fetchall() == [(instant_to_micros(wall_clock.now()),)]
    # Iteration is ORDER BY native_id: "31d6..." sorts before "aaaa..." (ASCII '3' < 'a').
    assert [line.message for line in reevaluation.observability.logger.lines] == [
        f"decisions for {_DL_NAME} ({_HASH_DL}): 062A none → download",
        f"decisions for {_CAT_NAME} ({_HASH_CAT}): 001A none → catalog",
    ]
    assert reevaluation.waker.woken_subjects == [WakeSubject.DOWNLOAD]


@pytest.mark.asyncio
async def test_unchanged_row_is_evaluated_but_not_written(
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _CAT_NAME), wall_clock.now(), _NODE_ID)
    )
    candidate = _reported_file(_HASH_CAT, _CAT_NAME).to_candidate()
    decisions = engine.evaluate_file((candidate,))
    assert decisions  # non-empty
    # pre-seed the "already correct" verdict
    decision_store.record_decision(
        DatedDecision(
            FileKey(Network.ED2K, _HASH_CAT), to_record(decisions[0]), wall_clock.now(), _NODE_ID
        )
    )
    reevaluation = _Reevaluation(
        observation_store, decision_store, catalog_scan_reader, engine, wall_clock
    )

    await reevaluation.run()

    assert reevaluation.logger.lines == [
        LoggedLine("info", "catalogue re-evaluated: 1 files, 0 rows written")
    ]
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 1
    assert reevaluation.observability.logger.lines == []
    assert reevaluation.waker.woken_subjects == []


@pytest.mark.asyncio
async def test_store_error_on_one_row_is_absorbed_and_sweep_continues(
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_DL, _DL_NAME), wall_clock.now(), _NODE_ID)
    )
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _CAT_NAME), wall_clock.now(), _NODE_ID)
    )
    # TEST trigger: makes the match_decisions INSERT fail for ONE hash only -> that row's
    # helper call raises StoreError, the other row must still be processed.
    catalog_connection.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON match_decisions"
        f" WHEN NEW.file_id = x'{FileKey(Network.ED2K, _HASH_DL).file_id.hex()}'"
        " BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    reevaluation = _Reevaluation(
        observation_store, decision_store, catalog_scan_reader, engine, wall_clock
    )

    await reevaluation.run()

    assert decision_tiers(catalog_connection) == [(_HASH_CAT, "catalog")]
    assert decision_store.read_latest_decisions(FileKey(Network.ED2K, _HASH_DL)) == {}
    assert reevaluation.logger.lines == [
        LoggedLine(
            "error",
            f"persistence failed on file=ed2k:{_HASH_DL} (injected failure):"
            " re-evaluation skipped, sweep continues",
        ),
        LoggedLine("info", "catalogue re-evaluated: 2 files, 1 rows written"),
    ]


@pytest.mark.asyncio
async def test_backfill_retracts_a_legacy_arbitrary_target_row(
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # §10: an old "unidentified" row under an arbitrary target_id (001A/catalog) is retracted
    # by the set-diff when the file becomes identified (062A + 062B) on the re-evaluation pass.
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_MULTI, _MULTI_NAME), wall_clock.now(), _NODE_ID)
    )
    decision_store.record_decision(
        DatedDecision(
            FileKey(Network.ED2K, _HASH_MULTI),
            DecisionRecord(TargetId("001A"), "keroro_large", DecisionTier.CATALOG),
            wall_clock.now(),
            _NODE_ID,
        )
    )
    reevaluation = _Reevaluation(
        observation_store, decision_store, catalog_scan_reader, engine, wall_clock
    )

    await reevaluation.run()

    assert reevaluation.logger.lines == [  # 062A + 062B + retract 001A
        LoggedLine("info", "catalogue re-evaluated: 1 files, 3 rows written")
    ]
    assert decision_store.read_latest_decisions(FileKey(Network.ED2K, _HASH_MULTI)) == {
        "062A": DecisionRecord(
            target_id=TargetId("062A"), rule_name="numero_nu_confirmed", tier=DecisionTier.DOWNLOAD
        ),
        "062B": DecisionRecord(
            target_id=TargetId("062B"), rule_name="numero_nu_confirmed", tier=DecisionTier.DOWNLOAD
        ),
        TargetId("001A"): Retraction(TargetId("001A")),
    }


@pytest.mark.asyncio
async def test_backfill_ignores_the_legacy_empty_sentinel(
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # §10: the old whole-file retraction sentinel (target_id="") is invisible to the set-diff.
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_MULTI, _MULTI_NAME), wall_clock.now(), _NODE_ID)
    )
    decision_store.record_decision(
        DatedDecision(
            FileKey(Network.ED2K, _HASH_MULTI), Retraction(TargetId("")), wall_clock.now(), _NODE_ID
        )
    )
    reevaluation = _Reevaluation(
        observation_store, decision_store, catalog_scan_reader, engine, wall_clock
    )

    await reevaluation.run()

    assert reevaluation.logger.lines == [  # only 062A + 062B; "" untouched
        LoggedLine("info", "catalogue re-evaluated: 1 files, 2 rows written")
    ]
    assert set(decision_store.read_latest_decisions(FileKey(Network.ED2K, _HASH_MULTI))) == {
        "062A",
        "062B",
    }
    assert (
        catalog_connection.execute(
            "SELECT count(*) FROM match_decisions WHERE target_id = ''"
        ).fetchone()[0]
        == 1
    )


@pytest.mark.asyncio
async def test_backfill_judges_a_hash_on_all_its_names_not_only_the_latest(
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    fake_time: FakeTime,
    wall_clock: FakeWallClock,
) -> None:
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_DL, _DL_NAME), wall_clock.now(), _NODE_ID)
    )
    fake_time.advance(timedelta(minutes=1))  # the latest name matches nothing
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_DL, "random.txt"), wall_clock.now(), _NODE_ID)
    )
    reevaluation = _Reevaluation(
        observation_store, decision_store, catalog_scan_reader, engine, wall_clock
    )

    await reevaluation.run()

    assert reevaluation.logger.lines == [
        LoggedLine("info", "catalogue re-evaluated: 1 files, 1 rows written")
    ]
    assert decision_store.read_latest_decisions(FileKey(Network.ED2K, _HASH_DL)) == {
        "062A": DecisionRecord(
            target_id=TargetId("062A"), rule_name="id_segment_exact", tier=DecisionTier.DOWNLOAD
        )
    }


@pytest.mark.asyncio
async def test_progress_is_logged_at_each_multiple_of_the_cadence_only(
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_DL, _DL_NAME), wall_clock.now(), _NODE_ID)
    )
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _CAT_NAME), wall_clock.now(), _NODE_ID)
    )
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_MULTI, "random.txt"), wall_clock.now(), _NODE_ID)
    )
    reevaluation = _Reevaluation(
        observation_store,
        decision_store,
        catalog_scan_reader,
        engine,
        wall_clock,
        progress_every_files=2,
    )

    await reevaluation.run()

    assert reevaluation.logger.lines == [
        LoggedLine("info", "catalogue re-evaluation: 2/3 files, 2 rows written"),
        LoggedLine("info", "catalogue re-evaluated: 3 files, 2 rows written"),
    ]
