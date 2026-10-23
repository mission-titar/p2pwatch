import sqlite3
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_source_point_store import (
    SqliteSourcePointStore,
)
from p2pwatch.application.steps.download_cycle import run_download_cycle
from p2pwatch.application.steps.download_deps import DownloadDeps
from p2pwatch.domain.client_errors import ClientUnreachableError
from p2pwatch.domain.download.states import DownloadState
from p2pwatch.domain.file_key import Network
from p2pwatch.domain.observability.events import SourceFirstUseful, SourceReappeared, TargetTitle
from p2pwatch.domain.source import (
    LatestPoint,
    SourceKey,
    SourcePoint,
    SourceReading,
    SourceRole,
)
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_event_emitter import FakeEventEmitter
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
from tests.fakes.adapters.driven.fake_source_client import FakeSourceClient
from tests.fakes.adapters.driven.fake_source_point_store import FakeSourcePointStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore
from tests.support.application.steps.download_deps import (
    HASH_A,
    HASH_B,
    HASH_C,
    NODE,
    build_deps,
    candidate,
    key,
    observation,
    status,
)
from tests.support.catalog_rows import insert_file, source_variant_node_ids


def _reading(name: str, role: SourceRole | None = SourceRole.QUEUED) -> SourceReading:
    return SourceReading(SourceKey(Network.ED2K, "1f" * 16), name, None, role, None, None, (), 0)


@pytest.mark.asyncio
async def test_the_sources_of_each_tracked_download_the_client_lists_are_recorded() -> None:
    # Stage 4, D8: the untracked C is not the crawler's, and each read_at precedes its read.
    fake_time = FakeTime()
    start = fake_time.wall.now()
    readings: dict[str, tuple[SourceReading, ...]] = {
        HASH_A: (_reading("peer A"),),
        HASH_B: (_reading("peer B", None),),
    }
    listed = (status(HASH_A), status(HASH_C), status(HASH_B))
    client = FakeDownloadClient(listed=[listed])
    source_client = FakeSourceClient(readings=readings, fake_time=fake_time)
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    tracked_download_store.states[HASH_B] = DownloadState.QUEUED
    sources = FakeSourcePointStore()
    deps = build_deps(
        client=client,
        source_client=source_client,
        tracked_download_store=tracked_download_store,
        sources=sources,
        fake_time=fake_time,
    )
    await run_download_cycle(deps, NODE)
    assert source_client.source_reads == [HASH_A, HASH_B]
    assert sources.recorded == [
        SourcePoint(key(HASH_A), readings[HASH_A][0], SourceRole.QUEUED, start, NODE),
        SourcePoint(
            key(HASH_B),
            readings[HASH_B][0],
            SourceRole.UNDETERMINED,
            start + timedelta(seconds=1),
            NODE,
        ),
    ]


@pytest.mark.asyncio
async def test_a_passing_reading_carries_its_latest_points_role_from_the_window_before_it() -> None:
    # The window spans three times between reads (source points spec, D4).
    fake_time = FakeTime()
    start = fake_time.wall.now()
    passing = _reading("peer", None)
    readings: dict[str, tuple[SourceReading, ...]] = {HASH_A: (_reading("peer"), passing)}
    sources = FakeSourcePointStore(latest=LatestPoint(SourceRole.SENDING, start, 0))
    deps = build_deps(
        client=FakeDownloadClient(listed=[(status(HASH_A),)]),
        source_client=FakeSourceClient(readings=readings),
        tracked_download_store=_tracking(HASH_A),
        sources=sources,
        fake_time=fake_time,
        time_between_source_reads=timedelta(minutes=5),
    )
    await run_download_cycle(deps, NODE)
    assert sources.latest_asked == [(HASH_A, passing, start - timedelta(minutes=15), start)]
    assert [point.role for point in sources.recorded] == [SourceRole.QUEUED] * 2


@pytest.mark.asyncio
async def test_a_reading_with_neither_source_nor_name_is_dropped() -> None:
    # Nothing could tell it from the next one (source points spec, D4).
    nameless = SourceReading(None, None, None, None, None, None, (), 0)
    readings: dict[str, tuple[SourceReading, ...]] = {HASH_A: (nameless, _reading("peer"))}
    sources = FakeSourcePointStore()
    deps = build_deps(
        client=FakeDownloadClient(listed=[(status(HASH_A),)]),
        source_client=FakeSourceClient(readings=readings),
        tracked_download_store=_tracking(HASH_A),
        sources=sources,
    )
    await run_download_cycle(deps, NODE)
    assert sources.latest_asked == []
    assert [point.reading for point in sources.recorded] == [_reading("peer")]


@pytest.mark.asyncio
async def test_a_download_the_client_reports_completed_is_not_read() -> None:
    client = FakeDownloadClient(listed=[(status(HASH_A, completed=True), status(HASH_B))])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    tracked_download_store.states[HASH_B] = DownloadState.DOWNLOADING
    source_client = FakeSourceClient()
    await run_download_cycle(
        build_deps(
            client=client,
            source_client=source_client,
            tracked_download_store=tracked_download_store,
        ),
        NODE,
    )
    assert source_client.source_reads == [HASH_B]


@pytest.mark.asyncio
async def test_a_store_failure_on_one_download_skips_its_sources_only() -> None:
    client = FakeDownloadClient(listed=[(status(HASH_A), status(HASH_B))])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    tracked_download_store.states[HASH_B] = DownloadState.DOWNLOADING
    sources = FakeSourcePointStore(fail_for={HASH_A})
    source_client = FakeSourceClient(readings={HASH_A: (_reading("a"),), HASH_B: (_reading("b"),)})
    await run_download_cycle(
        build_deps(
            client=client,
            source_client=source_client,
            tracked_download_store=tracked_download_store,
            sources=sources,
        ),
        NODE,
    )
    assert [point.file.native_id for point in sources.recorded] == [HASH_B]


@pytest.mark.asyncio
async def test_sources_are_read_once_per_interval_however_often_the_cycle_runs() -> None:
    # Source points spec, D3: rounds 30 s apart, sources every 300 s, the first round included.
    fake_time = FakeTime()
    start = fake_time.wall.now()
    client = FakeDownloadClient(listed=[(status(HASH_A),)] * 11)
    sources = FakeSourcePointStore()
    deps = build_deps(
        client=client,
        source_client=FakeSourceClient(readings={HASH_A: (_reading("peer"),)}),
        tracked_download_store=_tracking(HASH_A),
        sources=sources,
        fake_time=fake_time,
        sources_interval=timedelta(seconds=300),
    )
    for _ in range(11):
        await run_download_cycle(deps, NODE)
        fake_time.advance(timedelta(seconds=30))
    assert [point.observed_at for point in sources.recorded] == [
        start,
        start + timedelta(seconds=300),
    ]


@pytest.mark.asyncio
async def test_a_sources_read_the_daemon_failed_waits_for_the_next_interval() -> None:
    # The step's time is taken when it starts, so an unreachable client is not retried each poll.
    fake_time = FakeTime()
    client = FakeDownloadClient(listed=[(status(HASH_A),)] * 3)
    source_client = FakeSourceClient(source_failures=[ClientUnreachableError("down")])
    deps = build_deps(
        client=client,
        source_client=source_client,
        tracked_download_store=_tracking(HASH_A),
        fake_time=fake_time,
        sources_interval=timedelta(seconds=300),
    )
    await run_download_cycle(deps, NODE)
    fake_time.advance(timedelta(seconds=30))
    await run_download_cycle(deps, NODE)
    assert source_client.source_reads == [HASH_A]
    fake_time.advance(timedelta(seconds=270))
    await run_download_cycle(deps, NODE)
    assert source_client.source_reads == [HASH_A, HASH_A]


@pytest.mark.asyncio
async def test_a_wall_clock_step_back_delays_no_sources_read() -> None:
    fake_time = FakeTime()
    client = FakeDownloadClient(listed=[(status(HASH_A),)] * 2)
    source_client = FakeSourceClient()
    deps = build_deps(
        client=client,
        source_client=source_client,
        tracked_download_store=_tracking(HASH_A),
        fake_time=fake_time,
        sources_interval=timedelta(seconds=300),
    )
    await run_download_cycle(deps, NODE)
    fake_time.step_wall(timedelta(hours=-1))
    fake_time.advance(timedelta(seconds=300))
    await run_download_cycle(deps, NODE)
    assert source_client.source_reads == [HASH_A, HASH_A]


_PEER, _OTHER_PEER = SourceKey(Network.ED2K, "1f2e3d4c" * 4), SourceKey(Network.ED2K, "c" * 32)


def _read(
    source: SourceKey | None, source_name: str | None, role: SourceRole = SourceRole.QUEUED
) -> SourceReading:
    return SourceReading(source, source_name, None, role, None, None, (), 0)


def _tracking(*hashes: str) -> FakeTrackedDownloadStore:
    tracked_download_store = FakeTrackedDownloadStore()
    for native_id in hashes:
        tracked_download_store.states[native_id] = DownloadState.DOWNLOADING
    return tracked_download_store


@pytest.mark.asyncio
async def test_a_source_useful_on_two_files_in_one_round_is_new_once() -> None:
    # Stage 4, D9: the first file's event, named after its decision and best name.
    queued = (_read(_PEER, "AnimuseeFMR"),)
    source_client = FakeSourceClient(readings={HASH_A: queued, HASH_B: queued})
    decision_reader = FakeDecisionReader(candidates=(candidate(HASH_A, "062A"),))
    observation_reader = FakeObservationReader(
        best={HASH_A: observation(HASH_A, "Keroro 062.avi", 1)}
    )
    event_emitter = FakeEventEmitter()
    client = FakeDownloadClient(listed=[(status(HASH_A), status(HASH_B))])
    deps = build_deps(
        client=client,
        source_client=source_client,
        tracked_download_store=_tracking(HASH_A, HASH_B),
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        event_emitter=event_emitter,
    )
    await run_download_cycle(deps, NODE)
    alerts = [
        e for e in event_emitter.events if isinstance(e, SourceFirstUseful | SourceReappeared)
    ]
    assert alerts == [
        SourceFirstUseful(
            _PEER, "AnimuseeFMR", key(HASH_A), "Keroro 062.avi", (TargetTitle("062A", "t"),)
        )
    ]
    assert event_emitter.node_ids == {NODE}


@pytest.mark.asyncio
async def test_a_source_useful_again_after_the_threshold_reappears() -> None:
    # Each file asks the history before the round's start, not before its own read.
    fake_time = FakeTime()
    start = fake_time.wall.now()
    history: dict[SourceKey, tuple[LatestPoint, ...]] = {
        _PEER: (LatestPoint(SourceRole.QUEUED, start - timedelta(hours=13), 0),),
        _OTHER_PEER: (LatestPoint(SourceRole.QUEUED, start - timedelta(seconds=30), 0),),
    }
    readings: dict[str, tuple[SourceReading, ...]] = {
        HASH_A: (_read(_OTHER_PEER, None),),
        HASH_B: (_read(_PEER, "AnimuseeFMR", SourceRole.SENDING),),
    }
    sources = FakeSourcePointStore(history=history)
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.record_queued(
        key(HASH_B), "063A", 100, start
    )  # queued for it, no decision left
    tracked_download_store.states.update(
        {HASH_A: DownloadState.DOWNLOADING, HASH_B: DownloadState.DOWNLOADING}
    )
    event_emitter = FakeEventEmitter()
    client = FakeDownloadClient(listed=[(status(HASH_A), status(HASH_B))])
    deps = build_deps(
        client=client,
        source_client=FakeSourceClient(readings=readings, fake_time=fake_time),
        tracked_download_store=tracked_download_store,
        sources=sources,
        event_emitter=event_emitter,
        fake_time=fake_time,
    )
    await run_download_cycle(deps, NODE)
    assert sources.asked == [(_OTHER_PEER, start), (_PEER, start)]
    assert sources.node_ids == {NODE}  # the round writes and reads the cycle's node's points
    alerts = [
        e for e in event_emitter.events if isinstance(e, SourceFirstUseful | SourceReappeared)
    ]
    assert alerts == [
        SourceReappeared(
            _PEER, "AnimuseeFMR", key(HASH_B), HASH_B, (TargetTitle("063A", "t2"),), 46800.0
        )
    ]


@pytest.mark.asyncio
async def test_a_reading_without_a_source_id_raises_nothing() -> None:
    sources = FakeSourcePointStore()
    event_emitter = FakeEventEmitter()
    client = FakeDownloadClient(listed=[(status(HASH_A),)])
    deps = build_deps(
        client=client,
        source_client=FakeSourceClient(readings={HASH_A: (_read(None, "peer"),)}),
        tracked_download_store=_tracking(HASH_A),
        sources=sources,
        event_emitter=event_emitter,
    )
    await run_download_cycle(deps, NODE)
    assert sources.asked == []
    assert not any(
        isinstance(e, SourceFirstUseful | SourceReappeared) for e in event_emitter.events
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "readings",
    [
        (),
        (_read(None, "peer"),),
        (_read(_PEER, "peer", SourceRole.NOTHING_NEW),),
    ],
    ids=["none", "no-source-id", "not-useful"],
)
async def test_a_round_without_a_useful_reading_with_a_source_id_never_asks_for_the_baseline(
    readings: tuple[SourceReading, ...],
) -> None:
    sources = FakeSourcePointStore()
    client = FakeDownloadClient(listed=[(status(HASH_A),)])
    deps = build_deps(
        client=client,
        source_client=FakeSourceClient(readings={HASH_A: readings}),
        tracked_download_store=_tracking(HASH_A),
        sources=sources,
    )
    await run_download_cycle(deps, NODE)
    assert sources.baselines == []


@pytest.mark.asyncio
async def test_the_baseline_is_asked_once_per_round_against_its_start() -> None:
    fake_time = FakeTime()
    start = fake_time.wall.now()
    readings: dict[str, tuple[SourceReading, ...]] = {
        HASH_A: (_read(None, "peer"),),
        HASH_B: (_read(_PEER, "AnimuseeFMR"),),
        HASH_C: (_read(_OTHER_PEER, None, SourceRole.SENDING),),
    }
    sources = FakeSourcePointStore()
    client = FakeDownloadClient(listed=[(status(HASH_A), status(HASH_B), status(HASH_C))])
    deps = build_deps(
        client=client,
        source_client=FakeSourceClient(readings=readings, fake_time=fake_time),
        tracked_download_store=_tracking(HASH_A, HASH_B, HASH_C),
        sources=sources,
        fake_time=fake_time,
    )
    await run_download_cycle(deps, NODE)
    assert sources.baselines == [start]


@pytest.mark.asyncio
async def test_a_store_failure_asking_the_baseline_skips_that_downloads_alerts_only() -> None:
    queued = (_read(_PEER, "AnimuseeFMR"),)
    sources = FakeSourcePointStore(baseline_failures=1)
    event_emitter = FakeEventEmitter()
    client = FakeDownloadClient(listed=[(status(HASH_A), status(HASH_B))])
    deps = build_deps(
        client=client,
        source_client=FakeSourceClient(readings={HASH_A: queued, HASH_B: queued}),
        tracked_download_store=_tracking(HASH_A, HASH_B),
        sources=sources,
        event_emitter=event_emitter,
    )
    await run_download_cycle(deps, NODE)
    assert [point.file.native_id for point in sources.recorded] == [HASH_A, HASH_B]
    assert len(sources.baselines) == 2
    alerts = [
        e for e in event_emitter.events if isinstance(e, SourceFirstUseful | SourceReappeared)
    ]
    assert alerts == [SourceFirstUseful(_PEER, "AnimuseeFMR", key(HASH_B), HASH_B, ())]


@pytest.mark.asyncio
@pytest.mark.parametrize("order", [(HASH_A, HASH_B), (HASH_B, HASH_A)], ids=["a-first", "b-first"])
async def test_the_first_recording_round_is_a_baseline(
    tmp_path: Path, order: tuple[str, str]
) -> None:
    # On a real catalog: two queued sources in the node's first round, a third in the next.
    catalog = open_catalog(tmp_path / "catalog.db")
    for native_id in order:
        insert_file(catalog, native_id)
    readings: dict[str, tuple[SourceReading, ...]] = {
        HASH_A: (_peer(_PEER),),
        HASH_B: (_peer(_OTHER_PEER),),
    }
    fake_time = FakeTime()
    rounds = [tuple(status(h) for h in order)] * 2
    client = FakeDownloadClient(listed=rounds)
    event_emitter = FakeEventEmitter()
    deps = build_deps(
        client=client,
        source_client=FakeSourceClient(readings=readings, fake_time=fake_time),
        tracked_download_store=_tracking(HASH_A, HASH_B),
        sources=SqliteSourcePointStore(catalog),
        event_emitter=event_emitter,
        fake_time=fake_time,
    )
    await run_download_cycle(deps, NODE)
    alerts = [
        e for e in event_emitter.events if isinstance(e, SourceFirstUseful | SourceReappeared)
    ]
    assert alerts == []
    assert source_variant_node_ids(catalog) == {NODE}
    fake_time.advance(timedelta(seconds=30))
    third = SourceKey(Network.ED2K, "d" * 32)
    readings[HASH_A] = (_peer(_PEER), _peer(third))
    await run_download_cycle(deps, NODE)
    alerts = [
        e for e in event_emitter.events if isinstance(e, SourceFirstUseful | SourceReappeared)
    ]
    assert alerts == [SourceFirstUseful(third, "peer", key(HASH_A), HASH_A, ())]
    catalog.close()


def _peer(key: SourceKey, role: SourceRole = SourceRole.QUEUED) -> SourceReading:
    return SourceReading(key, "peer", None, role, None, None, (), 0)


@pytest.fixture
def real_catalog(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(tmp_path / "catalog.db")
    insert_file(catalog, HASH_A)
    yield catalog
    catalog.close()


def _real_deps(
    catalog: sqlite3.Connection,
    client: FakeDownloadClient,
    source_client: FakeSourceClient,
    event_emitter: FakeEventEmitter,
    fake_time: FakeTime,
) -> DownloadDeps:
    """``HASH_A`` tracked, its sources written to a real catalog."""
    sources = SqliteSourcePointStore(catalog)
    return build_deps(
        client=client,
        source_client=source_client,
        tracked_download_store=_tracking(HASH_A),
        sources=sources,
        event_emitter=event_emitter,
        fake_time=fake_time,
    )


def _alerts(event_emitter: FakeEventEmitter) -> list[object]:
    return [e for e in event_emitter.events if isinstance(e, SourceFirstUseful | SourceReappeared)]


@pytest.mark.asyncio
async def test_a_source_useful_at_three_consecutive_reads_is_new_once(
    real_catalog: sqlite3.Connection,
) -> None:
    # From its second read on, its earlier useful point is recent: no event (D5).
    readings: dict[str, tuple[SourceReading, ...]] = {HASH_A: (_peer(_OTHER_PEER),)}
    fake_time, event_emitter = FakeTime(), FakeEventEmitter()
    client = FakeDownloadClient(listed=[(status(HASH_A),)] * 4)
    source_client = FakeSourceClient(readings=readings, fake_time=fake_time)
    deps = _real_deps(real_catalog, client, source_client, event_emitter, fake_time)
    await run_download_cycle(deps, NODE)  # the node's first round, a baseline
    readings[HASH_A] = (_peer(_OTHER_PEER), _peer(_PEER))
    for _ in range(3):
        fake_time.advance(timedelta(seconds=30))
        await run_download_cycle(deps, NODE)
    assert _alerts(event_emitter) == [SourceFirstUseful(_PEER, "peer", key(HASH_A), HASH_A, ())]


@pytest.mark.asyncio
async def test_a_source_back_after_13_hours_through_an_undetermined_read_reappears(
    real_catalog: sqlite3.Connection,
) -> None:
    # An unknown point does not end an absence (stage 4, D9).
    readings: dict[str, tuple[SourceReading, ...]] = {HASH_A: (_peer(_PEER),)}
    fake_time, event_emitter = FakeTime(), FakeEventEmitter()
    client = FakeDownloadClient(listed=[(status(HASH_A),)] * 3)
    source_client = FakeSourceClient(readings=readings, fake_time=fake_time)
    deps = _real_deps(real_catalog, client, source_client, event_emitter, fake_time)
    last_useful = fake_time.wall.now()
    await run_download_cycle(deps, NODE)
    fake_time.advance(timedelta(hours=13))
    readings[HASH_A] = (_peer(_PEER, SourceRole.UNDETERMINED),)
    await run_download_cycle(deps, NODE)
    fake_time.advance(timedelta(seconds=30))
    readings[HASH_A] = (_peer(_PEER),)
    absent = (fake_time.wall.now() - last_useful).total_seconds()
    await run_download_cycle(deps, NODE)
    assert _alerts(event_emitter) == [
        SourceReappeared(_PEER, "peer", key(HASH_A), HASH_A, (), absent)
    ]
