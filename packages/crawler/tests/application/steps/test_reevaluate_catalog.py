"""Tests for the re-evaluation step ``reevaluate_catalog`` (spec §7, plan Task 5).

Real engine + real SQLite stores (same convention as ``test_decisions.py``: "real
stores on tmp_path"); only ``waker``/``event_emitter``/``wall_clock`` are fakes (``FakeWaker``/
``FakeEventEmitter``/``FakeWallClock``). Each hash under test is seeded via
``observation_store.record_observation`` first so it shows up in ``iter_latest_observations``
(the source the re-evaluation iterates).
"""

import sqlite3
from datetime import timedelta

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import (
    DecisionRecord,
    Explanation,
    MatchDecision,
    MatchingEngine,
)
from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_catalog_scan_reader import (
    SqliteCatalogScanReader,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.application.steps.reevaluate_catalog import ReevaluationSummary, reevaluate_catalog
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.file_target_decision import Retraction
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.wake_subject import WakeSubject
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.fakes.adapters.driven.fake_wall_clock import FakeWallClock
from tests.fakes.application.steps.fake_event_emitter import FakeEventEmitter
from tests.support.catalog_rows import decision_node_ids, decision_tiers

_NODE = "n1"
_HASH_DL = "31d6cfe0d16ae931b73c59d7e0c089c0"
_HASH_CAT = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_HASH_MULTI = "dddddddddddddddddddddddddddddddd"
_DL_NAME = "Keroro N°062A Les demoiselles cambrioleuses.avi"
_CAT_NAME = "keroro something.avi"
_MULTI_NAME = "Keroro 062 teletoon.avi"  # → 062A + 062B download (post-fan-out)


def _reported_file(native_id: str, filename: str) -> ReportedFile:
    return ReportedFile(
        file=FileKey(Network.ED2K, native_id),
        filename=filename,
        size_bytes=234_000_000,
        source_count=3,
        keyword="keroro",
    )


def _legacy_row(target_id: str, rule_name: str, tier: DecisionTier) -> MatchDecision:
    return MatchDecision(
        target_id=target_id,
        rule_name=rule_name,
        tier=tier,
        explanation=Explanation(
            target_id=target_id, rules_fired=(), tokens_matched=(), coverage_values=()
        ),
    )


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
        FileObservation(_reported_file(_HASH_DL, _DL_NAME), wall_clock.now()), _NODE
    )
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _CAT_NAME), wall_clock.now()), _NODE
    )
    event_emitter = FakeEventEmitter()
    waker = FakeWaker()
    summary = await reevaluate_catalog(
        observation_reader=observation_store,
        decision_writer=decision_store,
        decision_reader=decision_store,
        catalog_scan_reader=catalog_scan_reader,
        engine=engine,
        waker=waker,
        event_emitter=event_emitter,
        wall_clock=wall_clock,
        logger=FakeLogger(),
        node_id=_NODE,
        progress_every_files=200,
    )
    assert summary == ReevaluationSummary(files_evaluated=2, rows_written=2)
    tiers = dict(decision_tiers(catalog_connection))
    assert tiers == {_HASH_DL: "download", _HASH_CAT: "catalog"}
    assert decision_node_ids(catalog_connection) == {_NODE}
    decided_at = catalog_connection.execute("SELECT DISTINCT decided_at FROM match_decisions")
    assert decided_at.fetchall() == [(utc_iso(wall_clock.now()),)]
    assert len(event_emitter.events) == 2
    # Iteration is ORDER BY native_id: "31d6..." sorts before "aaaa..." (ASCII '3' < 'a').
    assert waker.woken_subjects == [WakeSubject.DOWNLOAD]


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
        FileObservation(_reported_file(_HASH_CAT, _CAT_NAME), wall_clock.now()), _NODE
    )
    candidate = _reported_file(_HASH_CAT, _CAT_NAME).to_candidate()
    decisions = engine.evaluate_file((candidate,))
    assert decisions  # non-empty
    # pre-seed the "already correct" verdict
    decision_store.record_decision(
        FileKey(Network.ED2K, _HASH_CAT), decisions[0], wall_clock.now(), _NODE
    )
    event_emitter = FakeEventEmitter()
    waker = FakeWaker()
    summary = await reevaluate_catalog(
        observation_reader=observation_store,
        decision_writer=decision_store,
        decision_reader=decision_store,
        catalog_scan_reader=catalog_scan_reader,
        engine=engine,
        waker=waker,
        event_emitter=event_emitter,
        wall_clock=wall_clock,
        logger=FakeLogger(),
        node_id=_NODE,
        progress_every_files=200,
    )
    assert summary == ReevaluationSummary(files_evaluated=1, rows_written=0)
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 1
    assert event_emitter.events == []
    assert waker.woken_subjects == []


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
        FileObservation(_reported_file(_HASH_DL, _DL_NAME), wall_clock.now()), _NODE
    )
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _CAT_NAME), wall_clock.now()), _NODE
    )
    logger = FakeLogger()
    # TEST trigger: makes the match_decisions INSERT fail for ONE hash only -> that row's
    # helper call raises StoreError, the other row must still be processed.
    catalog_connection.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON match_decisions"
        f" WHEN NEW.file_id = x'{FileKey(Network.ED2K, _HASH_DL).file_id.hex()}'"
        " BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    event_emitter = FakeEventEmitter()
    waker = FakeWaker()
    summary = await reevaluate_catalog(
        observation_reader=observation_store,
        decision_writer=decision_store,
        decision_reader=decision_store,
        catalog_scan_reader=catalog_scan_reader,
        engine=engine,
        waker=waker,
        event_emitter=event_emitter,
        wall_clock=wall_clock,
        logger=logger,
        node_id=_NODE,
        progress_every_files=200,
    )
    assert summary == ReevaluationSummary(files_evaluated=2, rows_written=1)
    assert decision_tiers(catalog_connection) == [(_HASH_CAT, "catalog")]
    assert decision_store.read_latest_decisions(FileKey(Network.ED2K, _HASH_DL)) == {}
    assert logger.lines == [
        LoggedLine(
            "error",
            f"persistence failed on file=ed2k:{_HASH_DL} (injected failure):"
            " re-evaluation skipped, sweep continues",
        )
    ]


@pytest.mark.asyncio
async def test_empty_catalogue_yields_zero_summary(
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    event_emitter = FakeEventEmitter()
    waker = FakeWaker()
    summary = await reevaluate_catalog(
        observation_reader=observation_store,
        decision_writer=decision_store,
        decision_reader=decision_store,
        catalog_scan_reader=catalog_scan_reader,
        engine=engine,
        waker=waker,
        event_emitter=event_emitter,
        wall_clock=wall_clock,
        logger=FakeLogger(),
        node_id=_NODE,
        progress_every_files=200,
    )
    assert summary == ReevaluationSummary(files_evaluated=0, rows_written=0)
    assert event_emitter.events == []
    assert waker.woken_subjects == []


@pytest.mark.asyncio
async def test_backfill_retracts_a_legacy_arbitrary_target_row(
    observation_store: SqliteObservationStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # §10: an old "unidentified" row under an arbitrary target_id (001A/catalog) is retracted
    # by the set-diff when the file becomes identified (062A + 062B) on the re-evaluation pass.
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_MULTI, _MULTI_NAME), wall_clock.now()), _NODE
    )
    decision_store.record_decision(
        FileKey(Network.ED2K, _HASH_MULTI),
        _legacy_row("001A", "keroro_large", DecisionTier.CATALOG),
        wall_clock.now(),
        _NODE,
    )
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    summary = await reevaluate_catalog(
        observation_reader=observation_store,
        decision_writer=decision_store,
        decision_reader=decision_store,
        catalog_scan_reader=catalog_scan_reader,
        engine=engine,
        waker=waker,
        event_emitter=event_emitter,
        wall_clock=wall_clock,
        logger=FakeLogger(),
        node_id=_NODE,
        progress_every_files=200,
    )
    assert summary == ReevaluationSummary(
        files_evaluated=1, rows_written=3
    )  # 062A + 062B + retract 001A
    assert decision_store.read_latest_decisions(FileKey(Network.ED2K, _HASH_MULTI)) == {
        "062A": DecisionRecord(
            target_id="062A", rule_name="numero_nu_confirmed", tier=DecisionTier.DOWNLOAD
        ),
        "062B": DecisionRecord(
            target_id="062B", rule_name="numero_nu_confirmed", tier=DecisionTier.DOWNLOAD
        ),
        "001A": Retraction("001A"),
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
        FileObservation(_reported_file(_HASH_MULTI, _MULTI_NAME), wall_clock.now()), _NODE
    )
    decision_store.record_retraction(
        FileKey(Network.ED2K, _HASH_MULTI), "", wall_clock.now(), _NODE
    )
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    summary = await reevaluate_catalog(
        observation_reader=observation_store,
        decision_writer=decision_store,
        decision_reader=decision_store,
        catalog_scan_reader=catalog_scan_reader,
        engine=engine,
        waker=waker,
        event_emitter=event_emitter,
        wall_clock=wall_clock,
        logger=FakeLogger(),
        node_id=_NODE,
        progress_every_files=200,
    )
    assert summary == ReevaluationSummary(
        files_evaluated=1, rows_written=2
    )  # only 062A + 062B; "" untouched
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
        FileObservation(_reported_file(_HASH_DL, _DL_NAME), wall_clock.now()), _NODE
    )
    fake_time.advance(timedelta(minutes=1))  # the latest name matches nothing
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_DL, "random.txt"), wall_clock.now()), _NODE
    )
    summary = await reevaluate_catalog(
        observation_reader=observation_store,
        decision_writer=decision_store,
        decision_reader=decision_store,
        catalog_scan_reader=catalog_scan_reader,
        engine=engine,
        waker=FakeWaker(),
        event_emitter=FakeEventEmitter(),
        wall_clock=wall_clock,
        logger=FakeLogger(),
        node_id=_NODE,
        progress_every_files=200,
    )
    assert summary == ReevaluationSummary(files_evaluated=1, rows_written=1)
    assert decision_store.read_latest_decisions(FileKey(Network.ED2K, _HASH_DL)) == {
        "062A": DecisionRecord(
            target_id="062A", rule_name="id_segment_exact", tier=DecisionTier.DOWNLOAD
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
    logger = FakeLogger()
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_DL, _DL_NAME), wall_clock.now()), _NODE
    )
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _CAT_NAME), wall_clock.now()), _NODE
    )
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_MULTI, "random.txt"), wall_clock.now()), _NODE
    )
    await reevaluate_catalog(
        observation_reader=observation_store,
        decision_writer=decision_store,
        decision_reader=decision_store,
        catalog_scan_reader=catalog_scan_reader,
        engine=engine,
        waker=FakeWaker(),
        event_emitter=FakeEventEmitter(),
        wall_clock=wall_clock,
        logger=logger,
        node_id=_NODE,
        progress_every_files=2,
    )
    assert logger.lines == [
        LoggedLine("info", "catalogue re-evaluation: 2/3 files, 2 rows written")
    ]
