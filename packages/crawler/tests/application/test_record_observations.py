import asyncio
import sqlite3
from datetime import timedelta

import pytest

from catalog_matching.domain.engine import MatchingEngine
from p2pwatch.adapters.driven.persistence_sqlite.catalog_repository import SqliteCatalogRepository
from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.driven.persistence_sqlite.variants import iso_to_micros
from p2pwatch.application.record_observations import record_observation
from p2pwatch.application.run_download_cycle import DOWNLOAD_WAKE_SUBJECT
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observability.events import ObservationRecorded
from p2pwatch.domain.observation import FileObservation
from p2pwatch_testing.application.fakes import (
    FakeTime,
    FakeWallClock,
    RecordingTelemetry,
    RecordingWakeHub,
)
from p2pwatch_testing.catalog_rows import count_observations

_HASH_DL = "31d6cfe0d16ae931b73c59d7e0c089c0"
_HASH_CAT = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_HASH_DISCARD = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_DL_NAME = "Keroro N°062A Les demoiselles cambrioleuses.avi"
# Pins a STABLE target via its unique title (062A/notify/title_review), unlike the catch-all
# "keroro something.avi" whose target_id is an arbitrary min-key over the present targets.
_NOTIFY_NAME = "Keroro Les demoiselles cambrioleuses.avi"


def _obs(ed2k_hash: str, filename: str) -> FileObservation:
    return FileObservation(
        file=FileKey(Network.ED2K, ed2k_hash),
        filename=filename,
        size_bytes=234_000_000,
        source_count=3,
        keyword="keroro",
    )


@pytest.mark.asyncio
async def test_observation_is_always_recorded_even_when_discarded(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    telemetry = RecordingTelemetry()
    wake_hub = RecordingWakeHub()
    changed = await record_observation(
        _obs(_HASH_DISCARD, "random.txt"),
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        client_name="amuled",
        channel="ed2k",
    )
    assert changed == 0
    assert count_observations(catalog_connection) == 1
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 0
    assert wake_hub.woken_subjects == []


@pytest.mark.asyncio
async def test_the_observation_carries_the_clocks_instant(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    await record_observation(
        _obs(_HASH_DISCARD, "random.txt"),
        catalog=catalog,
        engine=engine,
        wake_hub=RecordingWakeHub(),
        telemetry=RecordingTelemetry(),
        wall_clock=wall_clock,
        client_name="amuled",
        channel="ed2k",
    )
    observed_at = catalog_connection.execute("SELECT observed_at FROM observations").fetchone()
    assert observed_at == (iso_to_micros(utc_iso(wall_clock.now())),)


@pytest.mark.asyncio
async def test_new_verdict_is_persisted_and_nudged(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    telemetry = RecordingTelemetry()
    wake_hub = RecordingWakeHub()
    changed = await record_observation(
        _obs(_HASH_DL, _DL_NAME),
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        client_name="amuled",
        channel="ed2k",
    )
    assert changed == 1
    assert catalog_connection.execute("SELECT tier FROM match_decisions").fetchone() == (
        "download",
    )
    assert wake_hub.woken_subjects == [DOWNLOAD_WAKE_SUBJECT]


@pytest.mark.asyncio
async def test_unchanged_verdict_is_not_reappended_or_nudged(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    fake_time: FakeTime,
    wall_clock: FakeWallClock,
) -> None:
    telemetry = RecordingTelemetry()
    wake_hub = RecordingWakeHub()
    observation = _obs(_HASH_CAT, "keroro something.avi")
    assert (
        await record_observation(
            observation,
            catalog=catalog,
            engine=engine,
            wake_hub=wake_hub,
            telemetry=telemetry,
            wall_clock=wall_clock,
            client_name="amuled",
            channel="ed2k",
        )
        == 1
    )
    # Second observation of the SAME file a minute later: same catalog verdict → no re-append.
    fake_time.advance(timedelta(minutes=1))
    assert (
        await record_observation(
            observation,
            catalog=catalog,
            engine=engine,
            wake_hub=wake_hub,
            telemetry=telemetry,
            wall_clock=wall_clock,
            client_name="amuled",
            channel="ed2k",
        )
        == 0
    )
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 1
    # But the observation itself is re-persisted (periodic re-observation = the goal).
    assert count_observations(catalog_connection) == 2
    assert wake_hub.woken_subjects == []


@pytest.mark.asyncio
async def test_changed_verdict_is_reappended_and_nudged_again(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    telemetry = RecordingTelemetry()
    wake_hub = RecordingWakeHub()
    await record_observation(
        _obs(_HASH_DL, _NOTIFY_NAME),
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        client_name="amuled",
        channel="ed2k",
    )
    # 2nd view of the SAME hash, DOWNLOAD name → verdict changes → re-append + wake.
    changed = await record_observation(
        _obs(_HASH_DL, _DL_NAME),
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        client_name="amuled",
        channel="ed2k",
    )
    assert changed == 1
    tiers = [
        row[0]
        for row in catalog_connection.execute(
            "SELECT tier FROM match_decisions ORDER BY id"
        ).fetchall()
    ]
    assert tiers == ["notify", "download"]
    assert wake_hub.woken_subjects == [DOWNLOAD_WAKE_SUBJECT]


@pytest.mark.asyncio
async def test_persistence_error_is_absorbed_and_cycle_continues(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # TEST trigger: makes the observation INSERT fail → RepositoryError absorbed.
    catalog_connection.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON observations"
        " BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    telemetry = RecordingTelemetry()
    wake_hub = RecordingWakeHub()
    changed = await record_observation(
        _obs(_HASH_DL, _DL_NAME),
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        client_name="amuled",
        channel="ed2k",
    )
    assert changed == 0  # absorbed, the cycle continues
    assert wake_hub.woken_subjects == []
    assert f"file=ed2k:{_HASH_DL} " in caplog.text  # key=value, like the download side's hash=


@pytest.mark.asyncio
async def test_signal_consumer_awaits_the_nudge(
    catalog: SqliteCatalogRepository, engine: MatchingEngine, wall_clock: FakeWallClock
) -> None:
    # The hub IS consumed by an await (not dead code, DECISION 9): a consumer sleeps
    # on the subject and is woken by the post-commit wake.
    telemetry = RecordingTelemetry()
    wake_hub = RecordingWakeHub()
    waiter = asyncio.create_task(wake_hub.wait(DOWNLOAD_WAKE_SUBJECT))
    await asyncio.sleep(0)
    assert not waiter.done()
    await record_observation(
        _obs(_HASH_DL, _DL_NAME),
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        client_name="amuled",
        channel="ed2k",
    )
    await asyncio.wait_for(waiter, timeout=1.0)
    assert waiter.done()


@pytest.mark.asyncio
async def test_download_tier_verdict_also_nudges_the_download_subject(
    catalog: SqliteCatalogRepository,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # a NEW "download"-tier verdict wakes the "download" subject (the download loop, DECISION DV9).
    telemetry = RecordingTelemetry()
    wake_hub = RecordingWakeHub()
    changed = await record_observation(
        _obs(_HASH_DL, _DL_NAME),
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        client_name="amuled",
        channel="ed2k",
    )
    assert changed == 1
    assert wake_hub.woken_subjects == [DOWNLOAD_WAKE_SUBJECT]


@pytest.mark.asyncio
async def test_non_download_tier_verdict_does_not_nudge_the_download_subject(
    catalog: SqliteCatalogRepository,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # a "catalog"-tier verdict NEVER wakes the "download" subject.
    telemetry = RecordingTelemetry()
    wake_hub = RecordingWakeHub()
    changed = await record_observation(
        _obs(_HASH_CAT, "keroro something.avi"),
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        client_name="amuled",
        channel="ed2k",
    )
    assert changed == 1
    assert wake_hub.woken_subjects == []


@pytest.mark.asyncio
async def test_emits_observation_then_decision_on_change(
    catalog: SqliteCatalogRepository, engine: MatchingEngine, wall_clock: FakeWallClock
) -> None:
    telemetry = RecordingTelemetry()
    wake_hub = RecordingWakeHub()
    obs = _obs(_HASH_DL, _DL_NAME)  # matches at tier=download
    await record_observation(
        obs,
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        client_name="amuled",
        channel="ed2k",
    )
    kinds = [type(e).__name__ for e in telemetry.events]
    assert kinds == ["ObservationRecorded", "DecisionsRecorded"]
    assert telemetry.events[0] == ObservationRecorded(client_name="amuled", channel="ed2k")


@pytest.mark.asyncio
async def test_emits_only_observation_when_discarded(
    catalog: SqliteCatalogRepository, engine: MatchingEngine, wall_clock: FakeWallClock
) -> None:
    telemetry = RecordingTelemetry()
    obs = _obs(_HASH_DISCARD, "random.txt")  # discarded by the engine
    await record_observation(
        obs,
        catalog=catalog,
        engine=engine,
        wake_hub=RecordingWakeHub(),
        telemetry=telemetry,
        wall_clock=wall_clock,
        client_name="amuled",
        channel="kad",
    )
    assert [type(e).__name__ for e in telemetry.events] == ["ObservationRecorded"]


@pytest.mark.asyncio
async def test_multi_segment_observation_records_two_rows(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    telemetry = RecordingTelemetry()
    wake_hub = RecordingWakeHub()
    changed = await record_observation(
        _obs(_HASH_DL, "Keroro 062 teletoon.avi"),
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        client_name="amuled",
        channel="ed2k",
    )
    assert changed == 2
    assert catalog_connection.execute(
        "SELECT target_id FROM match_decisions ORDER BY id"
    ).fetchall() == [("062A",), ("062B",)]
