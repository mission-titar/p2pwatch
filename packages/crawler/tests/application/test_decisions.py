"""Tests for the shared decision helper (spec §7): set diff keyed by (hash, target_id).

Real engine + real SQLite catalog repo (mirrors ``test_record_observations.py``: "real repos
on tmp_path"); only ``wake_hub``/``telemetry``/``wall_clock`` are fakes. ``_record`` observes the
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
from p2pwatch.application.decisions import rejudge_file
from p2pwatch.application.record_observations import record_observation
from p2pwatch.application.run_download_cycle import DOWNLOAD_WAKE_SUBJECT
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observability.events import DecisionChange, DecisionsRecorded
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.retraction import RETRACTED_TIER
from p2pwatch_testing.application.fakes import (
    FakeLogger,
    FakeTime,
    FakeWallClock,
    RecordingTelemetry,
    RecordingWakeHub,
    TickingWallClock,
)
from p2pwatch_testing.catalog_rows import decision_node_ids, insert_file

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
    catalog: SqliteCatalogRepository, ed2k_hash: str, target_id: str, decided_at: datetime
) -> None:
    explanation = Explanation(
        target_id=target_id, rules_fired=(), tokens_matched=(), coverage_values=()
    )
    catalog.record_decision(
        _key(ed2k_hash),
        MatchDecision(target_id, "title_review", "notify", explanation),
        decided_at,
        _NODE,
    )


async def _record(
    ed2k_hash: str,
    filename: str,
    catalog: SqliteCatalogRepository,
    engine: MatchingEngine,
    wake_hub: RecordingWakeHub,
    telemetry: RecordingTelemetry,
    wall_clock: FakeWallClock,
) -> int:
    catalog.record_observation(
        FileObservation(_reported_file(ed2k_hash, filename), wall_clock.now()), _NODE
    )
    return await rejudge_file(
        _key(ed2k_hash),
        _reported_file(ed2k_hash, filename).to_candidate(),
        observation_reader=catalog,
        decision_writer=catalog,
        decision_reader=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        node_id=_NODE,
    )


@pytest.mark.asyncio
async def test_new_decision_is_recorded_emitted_and_nudged(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    written = await _record(_HASH_DL, _DL_NAME, catalog, engine, wake_hub, telemetry, wall_clock)
    assert written == 1
    assert catalog_connection.execute("SELECT target_id, tier FROM match_decisions").fetchone() == (
        "062A",
        "download",
    )
    assert decision_node_ids(catalog_connection) == {_NODE}
    assert telemetry.events == [
        _event(_HASH_DL, _DL_NAME, DecisionChange("062A", _TITLE_A, None, "download"))
    ]
    assert telemetry.node_ids == {_NODE}
    assert wake_hub.woken_subjects == [DOWNLOAD_WAKE_SUBJECT]


@pytest.mark.asyncio
async def test_multi_segment_file_records_both_segments_then_is_idempotent(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    written = await _record(
        _HASH_MULTI, _MULTI_NAME, catalog, engine, wake_hub, telemetry, wall_clock
    )
    assert written == 2
    assert catalog_connection.execute(
        "SELECT target_id, rule_name, tier FROM match_decisions ORDER BY id"
    ).fetchall() == [
        ("062A", "numero_nu_confirmed", "download"),
        ("062B", "numero_nu_confirmed", "download"),
    ]
    assert telemetry.events == [
        _event(
            _HASH_MULTI,
            _MULTI_NAME,
            DecisionChange("062A", _TITLE_A, None, "download"),
            DecisionChange("062B", _TITLE_B, None, "download"),
        )
    ]
    assert wake_hub.woken_subjects == [DOWNLOAD_WAKE_SUBJECT, DOWNLOAD_WAKE_SUBJECT]
    again = await _record(
        _HASH_MULTI, _MULTI_NAME, catalog, engine, wake_hub, telemetry, wall_clock
    )
    assert again == 0
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 2


@pytest.mark.asyncio
async def test_changed_decision_is_reappended_emitted_and_nudged(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    await _record(_HASH_DL, _NOTIFY_NAME, catalog, engine, wake_hub, telemetry, wall_clock)
    written = await _record(_HASH_DL, _DL_NAME, catalog, engine, wake_hub, telemetry, wall_clock)
    assert written == 1
    tiers = [
        row[0]
        for row in catalog_connection.execute(
            "SELECT tier FROM match_decisions ORDER BY id"
        ).fetchall()
    ]
    assert tiers == ["notify", "download"]
    assert [e.changes for e in telemetry.events if isinstance(e, DecisionsRecorded)] == [
        (DecisionChange("062A", _TITLE_A, None, "notify"),),
        (DecisionChange("062A", _TITLE_A, "notify", "download"),),
    ]
    assert wake_hub.woken_subjects == [DOWNLOAD_WAKE_SUBJECT]


@pytest.mark.asyncio
async def test_unchanged_decision_is_not_reappended_emitted_or_signalled(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    first = await _record(_HASH_CAT, _CAT_NAME, catalog, engine, wake_hub, telemetry, wall_clock)
    second = await _record(_HASH_CAT, _CAT_NAME, catalog, engine, wake_hub, telemetry, wall_clock)
    assert (first, second) == (1, 0)
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 1
    assert len(telemetry.events) == 1
    assert wake_hub.woken_subjects == []


@pytest.mark.asyncio
async def test_a_target_no_name_supports_is_retracted_without_nudge(
    catalog: SqliteCatalogRepository,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _DISCARD_NAME), wall_clock.now()), _NODE
    )
    _seed_decision(catalog, _HASH_CAT, "062A", wall_clock.now())
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    written = await _record(
        _HASH_CAT, _DISCARD_NAME, catalog, engine, wake_hub, telemetry, wall_clock
    )
    assert written == 1
    assert catalog.read_latest_decisions(_key(_HASH_CAT)) == {
        "062A": DecisionRecord(target_id="062A", rule_name="", tier=RETRACTED_TIER)
    }
    assert telemetry.events == [
        _event(_HASH_CAT, _DISCARD_NAME, DecisionChange("062A", _TITLE_A, "notify", RETRACTED_TIER))
    ]
    assert wake_hub.woken_subjects == []


@pytest.mark.asyncio
async def test_every_unsupported_target_is_retracted(
    catalog: SqliteCatalogRepository,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_MULTI, _DISCARD_NAME), wall_clock.now()), _NODE
    )
    _seed_decision(catalog, _HASH_MULTI, "062A", wall_clock.now())
    _seed_decision(catalog, _HASH_MULTI, "062B", wall_clock.now())
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    written = await _record(
        _HASH_MULTI, _DISCARD_NAME, catalog, engine, wake_hub, telemetry, wall_clock
    )
    assert written == 2
    assert catalog.read_latest_decisions(_key(_HASH_MULTI)) == {
        "062A": DecisionRecord(target_id="062A", rule_name="", tier=RETRACTED_TIER),
        "062B": DecisionRecord(target_id="062B", rule_name="", tier=RETRACTED_TIER),
    }
    assert len(telemetry.events) == 1


@pytest.mark.asyncio
async def test_already_retracted_then_none_is_a_no_op(
    catalog: SqliteCatalogRepository,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _DISCARD_NAME), wall_clock.now()), _NODE
    )
    _seed_decision(catalog, _HASH_CAT, "062A", wall_clock.now())
    catalog.record_retraction(_key(_HASH_CAT), "062A", wall_clock.now(), _NODE)
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    written = await _record(
        _HASH_CAT, _DISCARD_NAME, catalog, engine, wake_hub, telemetry, wall_clock
    )
    assert written == 0
    assert telemetry.events == []


@pytest.mark.asyncio
async def test_never_matched_then_none_is_a_no_op(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    written = await _record(
        _HASH_NEVER, _DISCARD_NAME, catalog, engine, wake_hub, telemetry, wall_clock
    )
    assert written == 0
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 0
    assert telemetry.events == []
    assert wake_hub.woken_subjects == []


@pytest.mark.asyncio
async def test_non_download_tier_decision_does_not_nudge_the_download_subject(
    catalog: SqliteCatalogRepository, engine: MatchingEngine, wall_clock: FakeWallClock
) -> None:
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    written = await _record(_HASH_CAT, _CAT_NAME, catalog, engine, wake_hub, telemetry, wall_clock)
    assert written == 1
    assert wake_hub.woken_subjects == []


@pytest.mark.asyncio
async def test_a_second_name_that_matches_nothing_does_not_retract_the_first(
    catalog: SqliteCatalogRepository,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # Regression (spec amuleapi-migration §8.4): names of one hash used to alternate verdicts.
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    written = [
        await record_observation(
            _reported_file(_HASH_DL, name),
            observation_writer=catalog,
            observation_reader=catalog,
            decision_writer=catalog,
            decision_reader=catalog,
            engine=engine,
            wake_hub=wake_hub,
            telemetry=telemetry,
            wall_clock=wall_clock,
            client_name="amuled",
            channel="ed2k",
            logger=FakeLogger(),
            node_id=_NODE,
        )
        for name in (_DL_NAME, _DISCARD_NAME, _DL_NAME, _DISCARD_NAME)
    ]
    assert written == [1, 0, 0, 0]
    assert catalog.read_latest_decisions(_key(_HASH_DL)) == {
        "062A": DecisionRecord(target_id="062A", rule_name="id_segment_exact", tier="download")
    }


@pytest.mark.asyncio
async def test_a_weaker_name_seen_again_does_not_downgrade_the_verdict(
    catalog: SqliteCatalogRepository,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    written = [
        await _record(_HASH_DL, name, catalog, engine, wake_hub, telemetry, wall_clock)
        for name in (_NOTIFY_NAME, _DL_NAME, _NOTIFY_NAME, _DL_NAME)
    ]
    assert written == [1, 1, 0, 0]
    assert catalog.read_latest_decisions(_key(_HASH_DL))["062A"].tier == "download"


@pytest.mark.asyncio
async def test_the_event_names_the_file_by_its_most_sourced_name(
    catalog: SqliteCatalogRepository, engine: MatchingEngine, wall_clock: FakeWallClock
) -> None:
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_DL, _DL_NAME, sources=9), wall_clock.now()), _NODE
    )
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    await _record(_HASH_DL, _NOTIFY_NAME, catalog, engine, wake_hub, telemetry, wall_clock)
    assert [e.filename for e in telemetry.events if isinstance(e, DecisionsRecorded)] == [_DL_NAME]


@pytest.mark.asyncio
async def test_a_retracted_target_gone_from_the_targets_has_no_title(
    catalog: SqliteCatalogRepository, engine: MatchingEngine, wall_clock: FakeWallClock
) -> None:
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _DISCARD_NAME), wall_clock.now()), _NODE
    )
    _seed_decision(catalog, _HASH_CAT, "999Z", wall_clock.now())
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    await _record(_HASH_CAT, _DISCARD_NAME, catalog, engine, wake_hub, telemetry, wall_clock)
    assert telemetry.events == [
        _event(_HASH_CAT, _DISCARD_NAME, DecisionChange("999Z", "", "notify", RETRACTED_TIER))
    ]


@pytest.mark.asyncio
async def test_a_file_with_no_name_left_is_named_by_the_candidate(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # Only a retraction can be written then, and it is never notified: the size is unknown.
    insert_file(catalog_connection, _HASH_CAT, 1)
    _seed_decision(catalog, _HASH_CAT, "062A", wall_clock.now())
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    await rejudge_file(
        _key(_HASH_CAT),
        _reported_file(_HASH_CAT, _DISCARD_NAME).to_candidate(),
        observation_reader=catalog,
        decision_writer=catalog,
        decision_reader=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        node_id=_NODE,
    )
    assert telemetry.events == [
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
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
) -> None:
    start = datetime(2026, 6, 12, tzinfo=UTC)
    seeded_at = start - timedelta(days=1)
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_MULTI, _MULTI_NAME), seeded_at), _NODE
    )
    _seed_decision(catalog, _HASH_MULTI, "001A", seeded_at)
    await rejudge_file(
        _key(_HASH_MULTI),
        _reported_file(_HASH_MULTI, _MULTI_NAME).to_candidate(),
        observation_reader=catalog,
        decision_writer=catalog,
        decision_reader=catalog,
        engine=engine,
        wake_hub=RecordingWakeHub(),
        telemetry=RecordingTelemetry(),
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
