"""Tests for ``FileJudge`` (spec §7): set diff keyed by (hash, target_id).

Real engine + real SQLite stores + the real dispatch step over fakes; ``waker`` and
``wall_clock`` are fakes. ``_record`` observes the name first: the judge reads every name the
catalog knows.
"""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord, MatchingEngine
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.file_target_decision import DatedDecision, Retraction
from p2pwatch.domain.observability.events import TargetTitle
from p2pwatch.domain.observability.notification import TierRise
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.wake_subject import WakeSubject
from tests.fakes.adapters.driven.fake_logger import LoggedLine
from tests.fakes.adapters.driven.fake_ticking_wall_clock import FakeTickingWallClock
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.fakes.adapters.driven.fake_wall_clock import FakeWallClock
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes
from tests.support.catalog_rows import decision_node_ids, insert_file

_NODE = "n1"
_HASH_DL = "31d6cfe0d16ae931b73c59d7e0c089c0"
_HASH_CAT = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_HASH_DISCARD = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_HASH_NEVER = "cccccccccccccccccccccccccccccccc"
_HASH_MULTI = "dddddddddddddddddddddddddddddddd"
_DL_NAME = "Keroro N°062A Les demoiselles cambrioleuses.avi"
_CAT_NAME = "keroro something.avi"
_DISCARD_NAME = "random.txt"
_MULTI_NAME = "Keroro 062 teletoon.avi"  # bare number + source marker → 062A + 062B download
# A file that pins a STABLE, specific target via its unique title (062A/notify/title_review),
# unlike _CAT_NAME whose catch-all target_id is an arbitrary min-key over the present targets.
_NOTIFY_NAME = "Keroro Les demoiselles cambrioleuses.avi"
_TITLE_A, _TITLE_B = "Les demoiselles cambrioleuses", "Le grand combat sous-marin"
_SIZE = 234_000_000
_ID_SEGMENT_DOWNLOAD = DecisionRecord(TargetId("062A"), "id_segment_exact", DecisionTier.DOWNLOAD)


def _key(native_id: str) -> FileKey:
    return FileKey(Network.ED2K, native_id)


def _decisions_line(native_id: str, filename: str, changes: str) -> LoggedLine:
    """The line the dispatch step logs for the file's ``DecisionsRecorded``."""
    return LoggedLine("info", f"decisions for {filename} ({native_id}): {changes}")


def _reported_file(native_id: str, filename: str, sources: int = 3) -> ReportedFile:
    return ReportedFile(
        file=FileKey(Network.ED2K, native_id),
        filename=filename,
        size_bytes=_SIZE,
        source_count=sources,
        keyword="keroro",
    )


def _seed_decision(
    decision_store: SqliteDecisionStore,
    native_id: str,
    target_id: TargetId,
    decided_at: datetime,
    node_id: str = _NODE,
) -> None:
    decision_store.record_decision(
        DatedDecision(
            _key(native_id),
            DecisionRecord(target_id, "title_review", DecisionTier.NOTIFY),
            decided_at,
            node_id,
        )
    )


def _file_judge(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    waker: FakeWaker,
    observability: ObservabilityOverFakes,
    wall_clock: WallClock,
) -> FileJudge:
    return FileJudge(
        observation_reader=observation_store,
        decision_writer=decision_store,
        decision_reader=decision_store,
        engine=engine,
        waker=waker,
        observability_dispatcher=observability.dispatcher,
        wall_clock=wall_clock,
    )


async def _record(
    native_id: str,
    filename: str,
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    waker: FakeWaker,
    observability: ObservabilityOverFakes,
    wall_clock: FakeWallClock,
) -> int:
    observation_store.record_observation(
        FileObservation(_reported_file(native_id, filename), wall_clock.now(), _NODE)
    )
    judge = _file_judge(observation_store, decision_store, engine, waker, observability, wall_clock)
    return await judge.rejudge(
        _key(native_id), _reported_file(native_id, filename).to_candidate(), _NODE
    )


@pytest.mark.asyncio
async def test_new_decision_is_recorded_emitted_and_nudged(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observability, waker = ObservabilityOverFakes(), FakeWaker()
    written = await _record(
        _HASH_DL,
        _DL_NAME,
        observation_store,
        decision_store,
        engine,
        waker,
        observability,
        wall_clock,
    )
    assert written == 1
    assert catalog_connection.execute("SELECT target_id, tier FROM match_decisions").fetchone() == (
        "062A",
        "download",
    )
    assert decision_node_ids(catalog_connection) == {_NODE}
    assert observability.logger.lines == [
        _decisions_line(_HASH_DL, _DL_NAME, "062A none → download")
    ]
    assert observability.notifier.node_ids == [_NODE]
    assert waker.woken_subjects == [WakeSubject.DOWNLOAD]


@pytest.mark.asyncio
async def test_multi_segment_file_records_both_segments_then_is_idempotent(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observability, waker = ObservabilityOverFakes(), FakeWaker()
    written = await _record(
        _HASH_MULTI,
        _MULTI_NAME,
        observation_store,
        decision_store,
        engine,
        waker,
        observability,
        wall_clock,
    )
    assert written == 2
    assert catalog_connection.execute(
        "SELECT target_id, rule_name, tier FROM match_decisions ORDER BY id"
    ).fetchall() == [
        ("062A", "numero_nu_confirmed", "download"),
        ("062B", "numero_nu_confirmed", "download"),
    ]
    assert observability.logger.lines == [
        _decisions_line(_HASH_MULTI, _MULTI_NAME, "062A none → download, 062B none → download")
    ]
    [(_, notification)] = observability.notifier.calls
    assert isinstance(notification, TierRise)
    assert (notification.tier, notification.target_titles) == (
        DecisionTier.DOWNLOAD,
        (TargetTitle(TargetId("062A"), _TITLE_A), TargetTitle(TargetId("062B"), _TITLE_B)),
    )
    assert waker.woken_subjects == [WakeSubject.DOWNLOAD, WakeSubject.DOWNLOAD]
    again = await _record(
        _HASH_MULTI,
        _MULTI_NAME,
        observation_store,
        decision_store,
        engine,
        waker,
        observability,
        wall_clock,
    )
    assert again == 0
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 2


@pytest.mark.asyncio
async def test_changed_decision_is_reappended_emitted_and_nudged(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observability, waker = ObservabilityOverFakes(), FakeWaker()
    await _record(
        _HASH_DL,
        _NOTIFY_NAME,
        observation_store,
        decision_store,
        engine,
        waker,
        observability,
        wall_clock,
    )
    written = await _record(
        _HASH_DL,
        _DL_NAME,
        observation_store,
        decision_store,
        engine,
        waker,
        observability,
        wall_clock,
    )
    assert written == 1
    tiers = [
        row[0]
        for row in catalog_connection.execute(
            "SELECT tier FROM match_decisions ORDER BY id"
        ).fetchall()
    ]
    assert tiers == ["notify", "download"]
    assert observability.logger.lines == [
        _decisions_line(_HASH_DL, _NOTIFY_NAME, "062A none → notify"),
        _decisions_line(_HASH_DL, _NOTIFY_NAME, "062A notify → download"),
    ]
    assert waker.woken_subjects == [WakeSubject.DOWNLOAD]


@pytest.mark.asyncio
async def test_unchanged_decision_is_not_reappended_emitted_or_signalled(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observability, waker = ObservabilityOverFakes(), FakeWaker()
    first = await _record(
        _HASH_CAT,
        _CAT_NAME,
        observation_store,
        decision_store,
        engine,
        waker,
        observability,
        wall_clock,
    )
    second = await _record(
        _HASH_CAT,
        _CAT_NAME,
        observation_store,
        decision_store,
        engine,
        waker,
        observability,
        wall_clock,
    )
    assert (first, second) == (1, 0)
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 1
    assert len(observability.logger.lines) == 1
    assert waker.woken_subjects == []


@pytest.mark.asyncio
async def test_a_target_no_name_supports_is_retracted_without_nudge(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _DISCARD_NAME), wall_clock.now(), _NODE)
    )
    _seed_decision(
        decision_store, _HASH_CAT, TargetId("062A"), wall_clock.now(), node_id="seed-node"
    )
    observability, waker = ObservabilityOverFakes(), FakeWaker()
    written = await _record(
        _HASH_CAT,
        _DISCARD_NAME,
        observation_store,
        decision_store,
        engine,
        waker,
        observability,
        wall_clock,
    )
    assert written == 1
    assert decision_store.read_latest_decisions(_key(_HASH_CAT)) == {
        TargetId("062A"): Retraction(TargetId("062A"))
    }
    assert decision_node_ids(catalog_connection) == {"seed-node", _NODE}
    assert observability.logger.lines == [
        _decisions_line(_HASH_CAT, _DISCARD_NAME, "062A notify → retracted")
    ]
    assert observability.notifier.calls == []
    assert waker.woken_subjects == []


@pytest.mark.asyncio
async def test_every_unsupported_target_is_retracted(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_MULTI, _DISCARD_NAME), wall_clock.now(), _NODE)
    )
    _seed_decision(decision_store, _HASH_MULTI, TargetId("062A"), wall_clock.now())
    _seed_decision(decision_store, _HASH_MULTI, TargetId("062B"), wall_clock.now())
    observability, waker = ObservabilityOverFakes(), FakeWaker()
    written = await _record(
        _HASH_MULTI,
        _DISCARD_NAME,
        observation_store,
        decision_store,
        engine,
        waker,
        observability,
        wall_clock,
    )
    assert written == 2
    assert decision_store.read_latest_decisions(_key(_HASH_MULTI)) == {
        TargetId("062A"): Retraction(TargetId("062A")),
        TargetId("062B"): Retraction(TargetId("062B")),
    }
    assert observability.logger.lines == [
        _decisions_line(
            _HASH_MULTI, _DISCARD_NAME, "062A notify → retracted, 062B notify → retracted"
        )
    ]


@pytest.mark.asyncio
async def test_already_retracted_then_none_is_a_no_op(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _DISCARD_NAME), wall_clock.now(), _NODE)
    )
    _seed_decision(decision_store, _HASH_CAT, TargetId("062A"), wall_clock.now())
    decision_store.record_decision(
        DatedDecision(_key(_HASH_CAT), Retraction(TargetId("062A")), wall_clock.now(), _NODE)
    )
    observability, waker = ObservabilityOverFakes(), FakeWaker()
    written = await _record(
        _HASH_CAT,
        _DISCARD_NAME,
        observation_store,
        decision_store,
        engine,
        waker,
        observability,
        wall_clock,
    )
    assert written == 0
    assert observability.logger.lines == []


@pytest.mark.asyncio
async def test_never_matched_then_none_is_a_no_op(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observability, waker = ObservabilityOverFakes(), FakeWaker()
    written = await _record(
        _HASH_NEVER,
        _DISCARD_NAME,
        observation_store,
        decision_store,
        engine,
        waker,
        observability,
        wall_clock,
    )
    assert written == 0
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 0
    assert observability.logger.lines == []
    assert waker.woken_subjects == []


@pytest.mark.asyncio
async def test_non_download_tier_decision_does_not_nudge_the_download_subject(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observability, waker = ObservabilityOverFakes(), FakeWaker()
    written = await _record(
        _HASH_CAT,
        _CAT_NAME,
        observation_store,
        decision_store,
        engine,
        waker,
        observability,
        wall_clock,
    )
    assert written == 1
    assert waker.woken_subjects == []


@pytest.mark.asyncio
async def test_a_second_name_that_matches_nothing_does_not_retract_the_first(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # Regression (spec amuleapi-migration §8.4): names of one hash used to alternate verdicts.
    observability, waker = ObservabilityOverFakes(), FakeWaker()
    written = [
        await _record(
            _HASH_DL,
            name,
            observation_store,
            decision_store,
            engine,
            waker,
            observability,
            wall_clock,
        )
        for name in (_DL_NAME, _DISCARD_NAME, _DL_NAME, _DISCARD_NAME)
    ]
    assert written == [1, 0, 0, 0]
    assert decision_store.read_latest_decisions(_key(_HASH_DL)) == {"062A": _ID_SEGMENT_DOWNLOAD}


@pytest.mark.asyncio
async def test_a_weaker_name_seen_again_does_not_downgrade_the_verdict(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observability, waker = ObservabilityOverFakes(), FakeWaker()
    written = [
        await _record(
            _HASH_DL,
            name,
            observation_store,
            decision_store,
            engine,
            waker,
            observability,
            wall_clock,
        )
        for name in (_NOTIFY_NAME, _DL_NAME, _NOTIFY_NAME, _DL_NAME)
    ]
    assert written == [1, 1, 0, 0]
    assert (
        decision_store.read_latest_decisions(_key(_HASH_DL))[TargetId("062A")]
        == _ID_SEGMENT_DOWNLOAD
    )


@pytest.mark.asyncio
async def test_the_event_names_the_file_by_its_most_sourced_name(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_DL, _DL_NAME, sources=9), wall_clock.now(), _NODE)
    )
    observability, waker = ObservabilityOverFakes(), FakeWaker()
    await _record(
        _HASH_DL,
        _NOTIFY_NAME,
        observation_store,
        decision_store,
        engine,
        waker,
        observability,
        wall_clock,
    )
    assert observability.logger.lines == [
        _decisions_line(_HASH_DL, _DL_NAME, "062A none → download")
    ]


@pytest.mark.asyncio
async def test_a_target_gone_from_the_targets_is_retracted(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _DISCARD_NAME), wall_clock.now(), _NODE)
    )
    _seed_decision(decision_store, _HASH_CAT, TargetId("999Z"), wall_clock.now())
    observability, waker = ObservabilityOverFakes(), FakeWaker()
    await _record(
        _HASH_CAT,
        _DISCARD_NAME,
        observation_store,
        decision_store,
        engine,
        waker,
        observability,
        wall_clock,
    )
    assert observability.logger.lines == [
        _decisions_line(_HASH_CAT, _DISCARD_NAME, "999Z notify → retracted")
    ]


@pytest.mark.asyncio
async def test_a_file_with_no_name_left_is_named_by_the_candidate(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # Only a retraction can be written then, and it is never notified: the size is unknown.
    insert_file(catalog_connection, _HASH_CAT, 1)
    _seed_decision(decision_store, _HASH_CAT, TargetId("062A"), wall_clock.now())
    observability, waker = ObservabilityOverFakes(), FakeWaker()
    judge = _file_judge(observation_store, decision_store, engine, waker, observability, wall_clock)
    await judge.rejudge(
        _key(_HASH_CAT), _reported_file(_HASH_CAT, _DISCARD_NAME).to_candidate(), _NODE
    )
    assert observability.logger.lines == [
        _decisions_line(_HASH_CAT, _DISCARD_NAME, "062A notify → retracted")
    ]


@pytest.mark.asyncio
async def test_each_row_carries_the_instant_read_right_before_its_write(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
) -> None:
    start = datetime(2026, 6, 12, tzinfo=UTC)
    seeded_at = start - timedelta(days=1)
    observation_store.record_observation(
        FileObservation(_reported_file(_HASH_MULTI, _MULTI_NAME), seeded_at, _NODE)
    )
    _seed_decision(decision_store, _HASH_MULTI, TargetId("001A"), seeded_at)
    judge = _file_judge(
        observation_store,
        decision_store,
        engine,
        FakeWaker(),
        ObservabilityOverFakes(),
        FakeTickingWallClock(FakeTime(start)),
    )
    await judge.rejudge(
        _key(_HASH_MULTI), _reported_file(_HASH_MULTI, _MULTI_NAME).to_candidate(), _NODE
    )
    rows = catalog_connection.execute(
        "SELECT target_id, tier, decided_at_micros FROM match_decisions ORDER BY id"
    ).fetchall()
    assert rows == [
        ("001A", "notify", instant_to_micros(seeded_at)),
        ("062A", "download", instant_to_micros(start)),
        ("062B", "download", instant_to_micros(start + timedelta(minutes=1))),
        ("001A", "retracted", instant_to_micros(start + timedelta(minutes=2))),
    ]
