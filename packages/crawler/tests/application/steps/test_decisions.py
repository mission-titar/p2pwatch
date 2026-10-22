"""Tests for the shared decision helper (spec §7): set diff keyed by (hash, target_id).

Real engine + real SQLite catalog repo (mirrors ``test_record_observations.py``: "real repos
on tmp_path"); only ``waker``/``event_emitter``/``wall_clock`` are fakes. ``_record`` observes the
name first: the helper judges the file on every name the catalog knows for it.
"""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from catalog_matching.domain.engine import (
    DecisionRecord,
    Explanation,
    MatchDecision,
    MatchingEngine,
)
from p2pwatch.adapters.driven.persistence_sqlite.catalog_repository import SqliteCatalogRepository
from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.application.steps.decisions import rejudge_file
from p2pwatch.application.steps.record_observations import record_observation
from p2pwatch.application.steps.run_download_cycle import DOWNLOAD_WAKE_SUBJECT
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observability.events import DecisionChange, DecisionsRecorded
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.retraction import RETRACTED_TIER
from tests.fakes.adapters.driven.fake_event_emitter import FakeEventEmitter
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.fakes.adapters.driven.fake_wall_clock import FakeWallClock
from tests.fakes.adapters.driven.ticking_wall_clock import TickingWallClock
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


def _key(ed2k_hash: str) -> FileKey:
    return FileKey(Network.ED2K, ed2k_hash)


def _event(ed2k_hash: str, filename: str, *changes: DecisionChange) -> DecisionsRecorded:
    return DecisionsRecorded(_key(ed2k_hash), filename, _SIZE, changes)


def _reported_file(ed2k_hash: str, filename: str, sources: int = 3) -> ReportedFile:
    return ReportedFile(
        file=FileKey(Network.ED2K, ed2k_hash),
        filename=filename,
        size_bytes=_SIZE,
        source_count=sources,
        keyword="keroro",
    )


def _seed_decision(
    decision_store: SqliteDecisionStore,
    ed2k_hash: str,
    target_id: str,
    decided_at: datetime,
    node_id: str = _NODE,
) -> None:
    explanation = Explanation(
        target_id=target_id, rules_fired=(), tokens_matched=(), coverage_values=()
    )
    decision_store.record_decision(
        _key(ed2k_hash),
        MatchDecision(target_id, "title_review", "notify", explanation),
        decided_at,
        node_id,
    )


async def _record(
    ed2k_hash: str,
    filename: str,
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    waker: FakeWaker,
    event_emitter: FakeEventEmitter,
    wall_clock: FakeWallClock,
) -> int:
    catalog.record_observation(
        FileObservation(_reported_file(ed2k_hash, filename), wall_clock.now()), _NODE
    )
    return await rejudge_file(
        _key(ed2k_hash),
        _reported_file(ed2k_hash, filename).to_candidate(),
        observation_reader=catalog,
        decision_writer=decision_store,
        decision_reader=decision_store,
        engine=engine,
        waker=waker,
        event_emitter=event_emitter,
        wall_clock=wall_clock,
        node_id=_NODE,
    )


@pytest.mark.asyncio
async def test_new_decision_is_recorded_emitted_and_nudged(
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    written = await _record(
        _HASH_DL, _DL_NAME, catalog, decision_store, engine, waker, event_emitter, wall_clock
    )
    assert written == 1
    assert catalog_connection.execute("SELECT target_id, tier FROM match_decisions").fetchone() == (
        "062A",
        "download",
    )
    assert decision_node_ids(catalog_connection) == {_NODE}
    assert event_emitter.events == [
        _event(_HASH_DL, _DL_NAME, DecisionChange("062A", _TITLE_A, None, "download"))
    ]
    assert event_emitter.node_ids == {_NODE}
    assert waker.woken_subjects == [DOWNLOAD_WAKE_SUBJECT]


@pytest.mark.asyncio
async def test_multi_segment_file_records_both_segments_then_is_idempotent(
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    written = await _record(
        _HASH_MULTI, _MULTI_NAME, catalog, decision_store, engine, waker, event_emitter, wall_clock
    )
    assert written == 2
    assert catalog_connection.execute(
        "SELECT target_id, rule_name, tier FROM match_decisions ORDER BY id"
    ).fetchall() == [
        ("062A", "numero_nu_confirmed", "download"),
        ("062B", "numero_nu_confirmed", "download"),
    ]
    assert event_emitter.events == [
        _event(
            _HASH_MULTI,
            _MULTI_NAME,
            DecisionChange("062A", _TITLE_A, None, "download"),
            DecisionChange("062B", _TITLE_B, None, "download"),
        )
    ]
    assert waker.woken_subjects == [DOWNLOAD_WAKE_SUBJECT, DOWNLOAD_WAKE_SUBJECT]
    again = await _record(
        _HASH_MULTI, _MULTI_NAME, catalog, decision_store, engine, waker, event_emitter, wall_clock
    )
    assert again == 0
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 2


@pytest.mark.asyncio
async def test_changed_decision_is_reappended_emitted_and_nudged(
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    await _record(
        _HASH_DL, _NOTIFY_NAME, catalog, decision_store, engine, waker, event_emitter, wall_clock
    )
    written = await _record(
        _HASH_DL, _DL_NAME, catalog, decision_store, engine, waker, event_emitter, wall_clock
    )
    assert written == 1
    tiers = [
        row[0]
        for row in catalog_connection.execute(
            "SELECT tier FROM match_decisions ORDER BY id"
        ).fetchall()
    ]
    assert tiers == ["notify", "download"]
    assert [e.changes for e in event_emitter.events if isinstance(e, DecisionsRecorded)] == [
        (DecisionChange("062A", _TITLE_A, None, "notify"),),
        (DecisionChange("062A", _TITLE_A, "notify", "download"),),
    ]
    assert waker.woken_subjects == [DOWNLOAD_WAKE_SUBJECT]


@pytest.mark.asyncio
async def test_unchanged_decision_is_not_reappended_emitted_or_signalled(
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    first = await _record(
        _HASH_CAT, _CAT_NAME, catalog, decision_store, engine, waker, event_emitter, wall_clock
    )
    second = await _record(
        _HASH_CAT, _CAT_NAME, catalog, decision_store, engine, waker, event_emitter, wall_clock
    )
    assert (first, second) == (1, 0)
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 1
    assert len(event_emitter.events) == 1
    assert waker.woken_subjects == []


@pytest.mark.asyncio
async def test_a_target_no_name_supports_is_retracted_without_nudge(
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _DISCARD_NAME), wall_clock.now()), _NODE
    )
    _seed_decision(decision_store, _HASH_CAT, "062A", wall_clock.now(), node_id="seed-node")
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    written = await _record(
        _HASH_CAT, _DISCARD_NAME, catalog, decision_store, engine, waker, event_emitter, wall_clock
    )
    assert written == 1
    assert decision_store.read_latest_decisions(_key(_HASH_CAT)) == {
        "062A": DecisionRecord(target_id="062A", rule_name="", tier=RETRACTED_TIER)
    }
    assert decision_node_ids(catalog_connection) == {"seed-node", _NODE}
    assert event_emitter.events == [
        _event(_HASH_CAT, _DISCARD_NAME, DecisionChange("062A", _TITLE_A, "notify", RETRACTED_TIER))
    ]
    assert waker.woken_subjects == []


@pytest.mark.asyncio
async def test_every_unsupported_target_is_retracted(
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_MULTI, _DISCARD_NAME), wall_clock.now()), _NODE
    )
    _seed_decision(decision_store, _HASH_MULTI, "062A", wall_clock.now())
    _seed_decision(decision_store, _HASH_MULTI, "062B", wall_clock.now())
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    written = await _record(
        _HASH_MULTI,
        _DISCARD_NAME,
        catalog,
        decision_store,
        engine,
        waker,
        event_emitter,
        wall_clock,
    )
    assert written == 2
    assert decision_store.read_latest_decisions(_key(_HASH_MULTI)) == {
        "062A": DecisionRecord(target_id="062A", rule_name="", tier=RETRACTED_TIER),
        "062B": DecisionRecord(target_id="062B", rule_name="", tier=RETRACTED_TIER),
    }
    assert len(event_emitter.events) == 1


@pytest.mark.asyncio
async def test_already_retracted_then_none_is_a_no_op(
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _DISCARD_NAME), wall_clock.now()), _NODE
    )
    _seed_decision(decision_store, _HASH_CAT, "062A", wall_clock.now())
    decision_store.record_retraction(_key(_HASH_CAT), "062A", wall_clock.now(), _NODE)
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    written = await _record(
        _HASH_CAT, _DISCARD_NAME, catalog, decision_store, engine, waker, event_emitter, wall_clock
    )
    assert written == 0
    assert event_emitter.events == []


@pytest.mark.asyncio
async def test_never_matched_then_none_is_a_no_op(
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    written = await _record(
        _HASH_NEVER,
        _DISCARD_NAME,
        catalog,
        decision_store,
        engine,
        waker,
        event_emitter,
        wall_clock,
    )
    assert written == 0
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 0
    assert event_emitter.events == []
    assert waker.woken_subjects == []


@pytest.mark.asyncio
async def test_non_download_tier_decision_does_not_nudge_the_download_subject(
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    written = await _record(
        _HASH_CAT, _CAT_NAME, catalog, decision_store, engine, waker, event_emitter, wall_clock
    )
    assert written == 1
    assert waker.woken_subjects == []


@pytest.mark.asyncio
async def test_a_second_name_that_matches_nothing_does_not_retract_the_first(
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # Regression (spec amuleapi-migration §8.4): names of one hash used to alternate verdicts.
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    written = [
        await record_observation(
            _reported_file(_HASH_DL, name),
            observation_writer=catalog,
            observation_reader=catalog,
            decision_writer=decision_store,
            decision_reader=decision_store,
            engine=engine,
            waker=waker,
            event_emitter=event_emitter,
            wall_clock=wall_clock,
            client_name="amuled",
            channel="ed2k",
            logger=FakeLogger(),
            node_id=_NODE,
        )
        for name in (_DL_NAME, _DISCARD_NAME, _DL_NAME, _DISCARD_NAME)
    ]
    assert written == [1, 0, 0, 0]
    assert decision_store.read_latest_decisions(_key(_HASH_DL)) == {
        "062A": DecisionRecord(target_id="062A", rule_name="id_segment_exact", tier="download")
    }


@pytest.mark.asyncio
async def test_a_weaker_name_seen_again_does_not_downgrade_the_verdict(
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    written = [
        await _record(
            _HASH_DL, name, catalog, decision_store, engine, waker, event_emitter, wall_clock
        )
        for name in (_NOTIFY_NAME, _DL_NAME, _NOTIFY_NAME, _DL_NAME)
    ]
    assert written == [1, 1, 0, 0]
    assert decision_store.read_latest_decisions(_key(_HASH_DL))["062A"].tier == "download"


@pytest.mark.asyncio
async def test_the_event_names_the_file_by_its_most_sourced_name(
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_DL, _DL_NAME, sources=9), wall_clock.now()), _NODE
    )
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    await _record(
        _HASH_DL, _NOTIFY_NAME, catalog, decision_store, engine, waker, event_emitter, wall_clock
    )
    assert [e.filename for e in event_emitter.events if isinstance(e, DecisionsRecorded)] == [
        _DL_NAME
    ]


@pytest.mark.asyncio
async def test_a_retracted_target_gone_from_the_targets_has_no_title(
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _DISCARD_NAME), wall_clock.now()), _NODE
    )
    _seed_decision(decision_store, _HASH_CAT, "999Z", wall_clock.now())
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    await _record(
        _HASH_CAT, _DISCARD_NAME, catalog, decision_store, engine, waker, event_emitter, wall_clock
    )
    assert event_emitter.events == [
        _event(_HASH_CAT, _DISCARD_NAME, DecisionChange("999Z", "", "notify", RETRACTED_TIER))
    ]


@pytest.mark.asyncio
async def test_a_file_with_no_name_left_is_named_by_the_candidate(
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # Only a retraction can be written then, and it is never notified: the size is unknown.
    insert_file(catalog_connection, _HASH_CAT, 1)
    _seed_decision(decision_store, _HASH_CAT, "062A", wall_clock.now())
    event_emitter, waker = FakeEventEmitter(), FakeWaker()
    await rejudge_file(
        _key(_HASH_CAT),
        _reported_file(_HASH_CAT, _DISCARD_NAME).to_candidate(),
        observation_reader=catalog,
        decision_writer=decision_store,
        decision_reader=decision_store,
        engine=engine,
        waker=waker,
        event_emitter=event_emitter,
        wall_clock=wall_clock,
        node_id=_NODE,
    )
    assert event_emitter.events == [
        DecisionsRecorded(
            _key(_HASH_CAT),
            _DISCARD_NAME,
            0,
            (DecisionChange("062A", _TITLE_A, "notify", RETRACTED_TIER),),
        )
    ]


@pytest.mark.asyncio
async def test_each_row_carries_the_instant_read_right_before_its_write(
    catalog: SqliteCatalogRepository,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
) -> None:
    start = datetime(2026, 6, 12, tzinfo=UTC)
    seeded_at = start - timedelta(days=1)
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_MULTI, _MULTI_NAME), seeded_at), _NODE
    )
    _seed_decision(decision_store, _HASH_MULTI, "001A", seeded_at)
    await rejudge_file(
        _key(_HASH_MULTI),
        _reported_file(_HASH_MULTI, _MULTI_NAME).to_candidate(),
        observation_reader=catalog,
        decision_writer=decision_store,
        decision_reader=decision_store,
        engine=engine,
        waker=FakeWaker(),
        event_emitter=FakeEventEmitter(),
        wall_clock=TickingWallClock(FakeTime(start)),
        node_id=_NODE,
    )
    rows = catalog_connection.execute(
        "SELECT target_id, tier, decided_at FROM match_decisions ORDER BY id"
    ).fetchall()
    assert rows == [
        ("001A", "notify", utc_iso(seeded_at)),
        ("062A", "download", utc_iso(start)),
        ("062B", "download", utc_iso(start + timedelta(minutes=1))),
        ("001A", RETRACTED_TIER, utc_iso(start + timedelta(minutes=2))),
    ]
