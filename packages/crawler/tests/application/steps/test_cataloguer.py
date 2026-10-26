import asyncio
import sqlite3
from datetime import timedelta

import pytest

from catalog_matching.domain.engine import MatchingEngine
from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.variants import iso_to_micros
from p2pwatch.application.steps.cataloguer import Cataloguer
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observability.node_metric import NodeCounter, NodeMetricSample
from p2pwatch.domain.observation import ReportedFile
from p2pwatch.domain.wake_subject import WakeSubject
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.fakes.adapters.driven.fake_wall_clock import FakeWallClock
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes
from tests.support.catalog_rows import (
    count_observations,
    decision_node_ids,
    observation_node_ids,
)

_NODE = "n1"
_HASH_DL = "31d6cfe0d16ae931b73c59d7e0c089c0"
_HASH_CAT = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_HASH_DISCARD = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_DL_NAME = "Keroro N°062A Les demoiselles cambrioleuses.avi"
# Pins a STABLE target via its unique title (062A/notify/title_review), unlike the catch-all
# "keroro something.avi" whose target_id is an arbitrary min-key over the present targets.
_NOTIFY_NAME = "Keroro Les demoiselles cambrioleuses.avi"


def _cataloguer(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
    waker: FakeWaker,
    observability_dispatcher: ObservabilityDispatcher,
    logger: FakeLogger,
) -> Cataloguer:
    file_judge = FileJudge(
        observation_reader=observation_store,
        decision_writer=decision_store,
        decision_reader=decision_store,
        engine=engine,
        waker=waker,
        observability_dispatcher=observability_dispatcher,
        wall_clock=wall_clock,
    )
    return Cataloguer(
        observation_writer=observation_store,
        file_judge=file_judge,
        observability_dispatcher=observability_dispatcher,
        wall_clock=wall_clock,
        logger=logger,
    )


def _reported_file(native_id: str, filename: str) -> ReportedFile:
    return ReportedFile(
        file=FileKey(Network.ED2K, native_id),
        filename=filename,
        size_bytes=234_000_000,
        source_count=3,
        keyword="keroro",
    )


@pytest.mark.asyncio
async def test_observation_is_always_recorded_even_when_discarded(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observability = ObservabilityOverFakes()
    waker = FakeWaker()
    changed = await _cataloguer(
        observation_store,
        decision_store,
        engine,
        wall_clock,
        waker,
        observability.dispatcher,
        FakeLogger(),
    ).catalog(_reported_file(_HASH_DISCARD, "random.txt"), "amuled", "ed2k", _NODE)
    assert changed == 0
    assert count_observations(catalog_connection) == 1
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 0
    assert waker.woken_subjects == []


@pytest.mark.asyncio
async def test_the_observation_carries_the_clocks_instant(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    await _cataloguer(
        observation_store,
        decision_store,
        engine,
        wall_clock,
        FakeWaker(),
        ObservabilityOverFakes().dispatcher,
        FakeLogger(),
    ).catalog(_reported_file(_HASH_DISCARD, "random.txt"), "amuled", "ed2k", _NODE)
    observed_at = catalog_connection.execute("SELECT observed_at FROM observations").fetchone()
    assert observed_at == (iso_to_micros(utc_iso(wall_clock.now())),)


@pytest.mark.asyncio
async def test_new_verdict_is_persisted_and_nudged(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observability = ObservabilityOverFakes()
    waker = FakeWaker()
    changed = await _cataloguer(
        observation_store,
        decision_store,
        engine,
        wall_clock,
        waker,
        observability.dispatcher,
        FakeLogger(),
    ).catalog(_reported_file(_HASH_DL, _DL_NAME), "amuled", "ed2k", _NODE)
    assert changed == 1
    assert catalog_connection.execute("SELECT tier FROM match_decisions").fetchone() == (
        "download",
    )
    assert observation_node_ids(catalog_connection) == decision_node_ids(catalog_connection)
    assert decision_node_ids(catalog_connection) == {_NODE}
    assert observability.notifier.node_ids == [_NODE]
    assert waker.woken_subjects == [WakeSubject.DOWNLOAD]


@pytest.mark.asyncio
async def test_unchanged_verdict_is_not_reappended_or_nudged(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    fake_time: FakeTime,
    wall_clock: FakeWallClock,
) -> None:
    observability = ObservabilityOverFakes()
    waker = FakeWaker()
    reported_file = _reported_file(_HASH_CAT, "keroro something.avi")
    assert (
        await _cataloguer(
            observation_store,
            decision_store,
            engine,
            wall_clock,
            waker,
            observability.dispatcher,
            FakeLogger(),
        ).catalog(reported_file, "amuled", "ed2k", _NODE)
        == 1
    )
    # Second observation of the SAME file a minute later: same catalog verdict → no re-append.
    fake_time.advance(timedelta(minutes=1))
    assert (
        await _cataloguer(
            observation_store,
            decision_store,
            engine,
            wall_clock,
            waker,
            observability.dispatcher,
            FakeLogger(),
        ).catalog(reported_file, "amuled", "ed2k", _NODE)
        == 0
    )
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 1
    # But the observation itself is re-persisted (periodic re-observation = the goal).
    assert count_observations(catalog_connection) == 2
    assert waker.woken_subjects == []


@pytest.mark.asyncio
async def test_changed_verdict_is_reappended_and_nudged_again(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observability = ObservabilityOverFakes()
    waker = FakeWaker()
    await _cataloguer(
        observation_store,
        decision_store,
        engine,
        wall_clock,
        waker,
        observability.dispatcher,
        FakeLogger(),
    ).catalog(_reported_file(_HASH_DL, _NOTIFY_NAME), "amuled", "ed2k", _NODE)
    # 2nd view of the SAME hash, DOWNLOAD name → verdict changes → re-append + wake.
    changed = await _cataloguer(
        observation_store,
        decision_store,
        engine,
        wall_clock,
        waker,
        observability.dispatcher,
        FakeLogger(),
    ).catalog(_reported_file(_HASH_DL, _DL_NAME), "amuled", "ed2k", _NODE)
    assert changed == 1
    tiers = [
        row[0]
        for row in catalog_connection.execute(
            "SELECT tier FROM match_decisions ORDER BY id"
        ).fetchall()
    ]
    assert tiers == ["notify", "download"]
    assert waker.woken_subjects == [WakeSubject.DOWNLOAD]


@pytest.mark.asyncio
async def test_persistence_error_is_absorbed_and_cycle_continues(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # TEST trigger: makes the observation INSERT fail → StoreError absorbed.
    catalog_connection.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON observations"
        " BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    observability = ObservabilityOverFakes()
    waker = FakeWaker()
    logger = FakeLogger()
    changed = await _cataloguer(
        observation_store,
        decision_store,
        engine,
        wall_clock,
        waker,
        observability.dispatcher,
        logger,
    ).catalog(_reported_file(_HASH_DL, _DL_NAME), "amuled", "ed2k", _NODE)
    assert changed == 0  # absorbed, the cycle continues
    assert waker.woken_subjects == []
    assert logger.lines == [  # file= as key=value, like the download side's
        LoggedLine(
            "error",
            f"persistence failed on file=ed2k:{_HASH_DL} (injected failure):"
            " observation skipped, cycle continues",
        )
    ]


@pytest.mark.asyncio
async def test_signal_consumer_awaits_the_nudge(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # The hub IS consumed by an await (not dead code, DECISION 9): a consumer sleeps
    # on the subject and is woken by the post-commit wake.
    observability = ObservabilityOverFakes()
    waker = FakeWaker()
    waiter = asyncio.create_task(waker.wait(WakeSubject.DOWNLOAD))
    await asyncio.sleep(0)
    assert not waiter.done()
    await _cataloguer(
        observation_store,
        decision_store,
        engine,
        wall_clock,
        waker,
        observability.dispatcher,
        FakeLogger(),
    ).catalog(_reported_file(_HASH_DL, _DL_NAME), "amuled", "ed2k", _NODE)
    await asyncio.wait_for(waiter, timeout=1.0)
    assert waiter.done()


@pytest.mark.asyncio
async def test_download_tier_verdict_also_nudges_the_download_subject(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # a NEW "download"-tier verdict wakes the "download" subject (the download loop, DECISION DV9).
    observability = ObservabilityOverFakes()
    waker = FakeWaker()
    changed = await _cataloguer(
        observation_store,
        decision_store,
        engine,
        wall_clock,
        waker,
        observability.dispatcher,
        FakeLogger(),
    ).catalog(_reported_file(_HASH_DL, _DL_NAME), "amuled", "ed2k", _NODE)
    assert changed == 1
    assert waker.woken_subjects == [WakeSubject.DOWNLOAD]


@pytest.mark.asyncio
async def test_non_download_tier_verdict_does_not_nudge_the_download_subject(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # a "catalog"-tier verdict NEVER wakes the "download" subject.
    observability = ObservabilityOverFakes()
    waker = FakeWaker()
    changed = await _cataloguer(
        observation_store,
        decision_store,
        engine,
        wall_clock,
        waker,
        observability.dispatcher,
        FakeLogger(),
    ).catalog(_reported_file(_HASH_CAT, "keroro something.avi"), "amuled", "ed2k", _NODE)
    assert changed == 1
    assert waker.woken_subjects == []


@pytest.mark.asyncio
async def test_emits_observation_then_decision_on_change(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observability = ObservabilityOverFakes()
    waker = FakeWaker()
    reported_file = _reported_file(_HASH_DL, _DL_NAME)  # matches at tier=download
    await _cataloguer(
        observation_store,
        decision_store,
        engine,
        wall_clock,
        waker,
        observability.dispatcher,
        FakeLogger(),
    ).catalog(reported_file, "amuled", "ed2k", _NODE)
    assert observability.logger.lines == [
        LoggedLine("debug", "observation recorded (ed2k)"),
        LoggedLine("info", f"decisions for {_DL_NAME} ({_HASH_DL}): 062A none → download"),
    ]
    assert (
        NodeMetricSample(NodeCounter.OBSERVATIONS, (("client", "amuled"), ("channel", "ed2k")), 1.0)
        in observability.node_metric_store.read_samples()
    )


@pytest.mark.asyncio
async def test_emits_only_observation_when_discarded(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observability = ObservabilityOverFakes()
    reported_file = _reported_file(_HASH_DISCARD, "random.txt")  # discarded by the engine
    await _cataloguer(
        observation_store,
        decision_store,
        engine,
        wall_clock,
        FakeWaker(),
        observability.dispatcher,
        FakeLogger(),
    ).catalog(reported_file, "amuled", "kad", _NODE)
    assert observability.logger.lines == [LoggedLine("debug", "observation recorded (kad)")]


@pytest.mark.asyncio
async def test_multi_segment_observation_records_two_rows(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observability = ObservabilityOverFakes()
    waker = FakeWaker()
    changed = await _cataloguer(
        observation_store,
        decision_store,
        engine,
        wall_clock,
        waker,
        observability.dispatcher,
        FakeLogger(),
    ).catalog(_reported_file(_HASH_DL, "Keroro 062 teletoon.avi"), "amuled", "ed2k", _NODE)
    assert changed == 2
    assert catalog_connection.execute(
        "SELECT target_id FROM match_decisions ORDER BY id"
    ).fetchall() == [("062A",), ("062B",)]
