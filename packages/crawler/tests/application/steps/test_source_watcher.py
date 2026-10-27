import sqlite3
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_source_point_store import (
    SqliteSourcePointStore,
)
from p2pwatch.application.steps.download_cycle import DownloadCycle
from p2pwatch.domain.client_errors import ClientUnreachableError
from p2pwatch.domain.download.states import DownloadState
from p2pwatch.domain.file_key import Network
from p2pwatch.domain.observability.events import TargetTitle
from p2pwatch.domain.observability.notification import SourceAlert, SourceAlertKind
from p2pwatch.domain.source import (
    LatestPoint,
    SourceKey,
    SourcePoint,
    SourceReading,
    SourceRole,
)
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
from tests.fakes.adapters.driven.fake_source_client import FakeSourceClient
from tests.fakes.adapters.driven.fake_source_point_store import FakeSourcePointStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_catalog
from tests.support.application.steps.download_cycle import (
    HASH_A,
    HASH_B,
    HASH_C,
    NODE,
    build_cycle,
    candidate,
    key,
    observation,
    status,
)
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes
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
    cycle = build_cycle(
        client=client,
        source_client=source_client,
        tracked_download_store=tracked_download_store,
        sources=sources,
        fake_time=fake_time,
    )
    await cycle.run(NODE)
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
    cycle = build_cycle(
        client=FakeDownloadClient(listed=[(status(HASH_A),)]),
        source_client=FakeSourceClient(readings=readings),
        tracked_download_store=_tracking(HASH_A),
        sources=sources,
        fake_time=fake_time,
        time_between_source_reads=timedelta(minutes=5),
    )
    await cycle.run(NODE)
    assert sources.latest_asked == [(HASH_A, passing, start - timedelta(minutes=15), start)]
    assert [point.role for point in sources.recorded] == [SourceRole.QUEUED] * 2


@pytest.mark.asyncio
async def test_a_reading_with_neither_source_nor_name_is_dropped() -> None:
    # Nothing could tell it from the next one (source points spec, D4).
    nameless = SourceReading(None, None, None, None, None, None, (), 0)
    readings: dict[str, tuple[SourceReading, ...]] = {HASH_A: (nameless, _reading("peer"))}
    sources = FakeSourcePointStore()
    cycle = build_cycle(
        client=FakeDownloadClient(listed=[(status(HASH_A),)]),
        source_client=FakeSourceClient(readings=readings),
        tracked_download_store=_tracking(HASH_A),
        sources=sources,
    )
    await cycle.run(NODE)
    assert sources.latest_asked == []
    assert [point.reading for point in sources.recorded] == [_reading("peer")]


@pytest.mark.asyncio
async def test_a_download_the_client_reports_completed_is_not_read() -> None:
    client = FakeDownloadClient(listed=[(status(HASH_A, completed=True), status(HASH_B))])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    tracked_download_store.states[HASH_B] = DownloadState.DOWNLOADING
    source_client = FakeSourceClient()
    await build_cycle(
        client=client,
        source_client=source_client,
        tracked_download_store=tracked_download_store,
    ).run(NODE)
    assert source_client.source_reads == [HASH_B]


@pytest.mark.asyncio
async def test_a_store_failure_on_one_download_skips_its_sources_only() -> None:
    client = FakeDownloadClient(listed=[(status(HASH_A), status(HASH_B))])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    tracked_download_store.states[HASH_B] = DownloadState.DOWNLOADING
    sources = FakeSourcePointStore(fail_for={HASH_A})
    source_client = FakeSourceClient(readings={HASH_A: (_reading("a"),), HASH_B: (_reading("b"),)})
    await build_cycle(
        client=client,
        source_client=source_client,
        tracked_download_store=tracked_download_store,
        sources=sources,
    ).run(NODE)
    assert [point.file.native_id for point in sources.recorded] == [HASH_B]


@pytest.mark.asyncio
async def test_sources_are_read_once_per_interval_however_often_the_cycle_runs() -> None:
    # Source points spec, D3: rounds 30 s apart, sources every 300 s, the first round included.
    fake_time = FakeTime()
    start = fake_time.wall.now()
    client = FakeDownloadClient(listed=[(status(HASH_A),)] * 11)
    sources = FakeSourcePointStore()
    cycle = build_cycle(
        client=client,
        source_client=FakeSourceClient(readings={HASH_A: (_reading("peer"),)}),
        tracked_download_store=_tracking(HASH_A),
        sources=sources,
        fake_time=fake_time,
        sources_interval=timedelta(seconds=300),
    )
    for _ in range(11):
        await cycle.run(NODE)
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
    cycle = build_cycle(
        client=client,
        source_client=source_client,
        tracked_download_store=_tracking(HASH_A),
        fake_time=fake_time,
        sources_interval=timedelta(seconds=300),
    )
    await cycle.run(NODE)
    fake_time.advance(timedelta(seconds=30))
    await cycle.run(NODE)
    assert source_client.source_reads == [HASH_A]
    fake_time.advance(timedelta(seconds=270))
    await cycle.run(NODE)
    assert source_client.source_reads == [HASH_A, HASH_A]


@pytest.mark.asyncio
async def test_a_wall_clock_step_back_delays_no_sources_read() -> None:
    fake_time = FakeTime()
    client = FakeDownloadClient(listed=[(status(HASH_A),)] * 2)
    source_client = FakeSourceClient()
    cycle = build_cycle(
        client=client,
        source_client=source_client,
        tracked_download_store=_tracking(HASH_A),
        fake_time=fake_time,
        sources_interval=timedelta(seconds=300),
    )
    await cycle.run(NODE)
    fake_time.step_wall(timedelta(hours=-1))
    fake_time.advance(timedelta(seconds=300))
    await cycle.run(NODE)
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
    observability = ObservabilityOverFakes()
    client = FakeDownloadClient(listed=[(status(HASH_A), status(HASH_B))])
    cycle = build_cycle(
        client=client,
        source_client=source_client,
        tracked_download_store=_tracking(HASH_A, HASH_B),
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        observability_dispatcher=observability.dispatcher,
    )
    await cycle.run(NODE)
    assert _alerts(observability) == [
        _alert(_PEER, "AnimuseeFMR", None, "Keroro 062.avi", (TargetTitle("062A", "t"),))
    ]
    assert observability.notifier.node_ids == [NODE]


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
    observability = ObservabilityOverFakes()
    client = FakeDownloadClient(listed=[(status(HASH_A), status(HASH_B))])
    cycle = build_cycle(
        client=client,
        source_client=FakeSourceClient(readings=readings, fake_time=fake_time),
        tracked_download_store=tracked_download_store,
        sources=sources,
        observability_dispatcher=observability.dispatcher,
        fake_time=fake_time,
    )
    await cycle.run(NODE)
    assert sources.asked == [(_OTHER_PEER, start), (_PEER, start)]
    assert sources.node_ids == {NODE}  # the round writes and reads the cycle's node's points
    assert _alerts(observability) == [
        _alert(_PEER, "AnimuseeFMR", timedelta(hours=13), HASH_B, (TargetTitle("063A", "t2"),))
    ]


@pytest.mark.asyncio
async def test_a_reading_without_a_source_id_raises_nothing() -> None:
    sources = FakeSourcePointStore()
    observability = ObservabilityOverFakes()
    client = FakeDownloadClient(listed=[(status(HASH_A),)])
    cycle = build_cycle(
        client=client,
        source_client=FakeSourceClient(readings={HASH_A: (_read(None, "peer"),)}),
        tracked_download_store=_tracking(HASH_A),
        sources=sources,
        observability_dispatcher=observability.dispatcher,
    )
    await cycle.run(NODE)
    assert sources.asked == []
    assert _alerts(observability) == []


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
    cycle = build_cycle(
        client=client,
        source_client=FakeSourceClient(readings={HASH_A: readings}),
        tracked_download_store=_tracking(HASH_A),
        sources=sources,
    )
    await cycle.run(NODE)
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
    cycle = build_cycle(
        client=client,
        source_client=FakeSourceClient(readings=readings, fake_time=fake_time),
        tracked_download_store=_tracking(HASH_A, HASH_B, HASH_C),
        sources=sources,
        fake_time=fake_time,
    )
    await cycle.run(NODE)
    assert sources.baselines == [start]


@pytest.mark.asyncio
async def test_a_store_failure_asking_the_baseline_skips_that_downloads_alerts_only() -> None:
    queued = (_read(_PEER, "AnimuseeFMR"),)
    sources = FakeSourcePointStore(baseline_failures=1)
    observability = ObservabilityOverFakes()
    client = FakeDownloadClient(listed=[(status(HASH_A), status(HASH_B))])
    cycle = build_cycle(
        client=client,
        source_client=FakeSourceClient(readings={HASH_A: queued, HASH_B: queued}),
        tracked_download_store=_tracking(HASH_A, HASH_B),
        sources=sources,
        observability_dispatcher=observability.dispatcher,
    )
    await cycle.run(NODE)
    assert [point.file.native_id for point in sources.recorded] == [HASH_A, HASH_B]
    assert len(sources.baselines) == 2
    assert _alerts(observability) == [_alert(_PEER, "AnimuseeFMR", None, HASH_B)]


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
    observability = ObservabilityOverFakes()
    cycle = build_cycle(
        client=client,
        source_client=FakeSourceClient(readings=readings, fake_time=fake_time),
        tracked_download_store=_tracking(HASH_A, HASH_B),
        sources=SqliteSourcePointStore(catalog),
        observability_dispatcher=observability.dispatcher,
        fake_time=fake_time,
    )
    await cycle.run(NODE)
    assert _alerts(observability) == []
    assert source_variant_node_ids(catalog) == {NODE}
    fake_time.advance(timedelta(seconds=30))
    third = SourceKey(Network.ED2K, "d" * 32)
    readings[HASH_A] = (_peer(_PEER), _peer(third))
    await cycle.run(NODE)
    assert _alerts(observability) == [_alert(third, "peer", None, HASH_A)]
    catalog.close()


def _peer(key: SourceKey, role: SourceRole = SourceRole.QUEUED) -> SourceReading:
    return SourceReading(key, "peer", None, role, None, None, (), 0)


@pytest.fixture
def real_catalog(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(tmp_path / "catalog.db")
    insert_file(catalog, HASH_A)
    yield catalog
    catalog.close()


def _real_cycle(
    catalog: sqlite3.Connection,
    client: FakeDownloadClient,
    source_client: FakeSourceClient,
    observability: ObservabilityOverFakes,
    fake_time: FakeTime,
) -> DownloadCycle:
    """``HASH_A`` tracked, its sources written to a real catalog."""
    sources = SqliteSourcePointStore(catalog)
    return build_cycle(
        client=client,
        source_client=source_client,
        tracked_download_store=_tracking(HASH_A),
        sources=sources,
        observability_dispatcher=observability.dispatcher,
        fake_time=fake_time,
    )


def _alerts(observability: ObservabilityOverFakes) -> list[SourceAlert]:
    """The source alerts, the only notifications of a round without completion."""
    alerts = []
    for _, notification in observability.notifier.calls:
        assert isinstance(notification, SourceAlert)
        alerts.append(notification)
    return alerts


def _alert(
    source: SourceKey,
    source_name: str,
    absent_for: timedelta | None,
    filename: str,
    target_titles: tuple[TargetTitle, ...] = (),
) -> SourceAlert:
    """The cycle's node's alert: a first useful source, or one ``absent_for`` that long."""
    kind = SourceAlertKind.FIRST_USEFUL if absent_for is None else SourceAlertKind.REAPPEARED
    return SourceAlert(kind, source, source_name, absent_for, target_titles, filename, NODE)


@pytest.mark.asyncio
async def test_a_source_useful_at_three_consecutive_reads_is_new_once(
    real_catalog: sqlite3.Connection,
) -> None:
    # From its second read on, its earlier useful point is recent: no event (D5).
    readings: dict[str, tuple[SourceReading, ...]] = {HASH_A: (_peer(_OTHER_PEER),)}
    fake_time, observability = FakeTime(), ObservabilityOverFakes()
    client = FakeDownloadClient(listed=[(status(HASH_A),)] * 4)
    source_client = FakeSourceClient(readings=readings, fake_time=fake_time)
    cycle = _real_cycle(real_catalog, client, source_client, observability, fake_time)
    await cycle.run(NODE)  # the node's first round, a baseline
    readings[HASH_A] = (_peer(_OTHER_PEER), _peer(_PEER))
    for _ in range(3):
        fake_time.advance(timedelta(seconds=30))
        await cycle.run(NODE)
    assert _alerts(observability) == [_alert(_PEER, "peer", None, HASH_A)]


@pytest.mark.asyncio
async def test_a_source_back_after_13_hours_through_an_undetermined_read_reappears(
    real_catalog: sqlite3.Connection,
) -> None:
    # An unknown point does not end an absence (stage 4, D9).
    readings: dict[str, tuple[SourceReading, ...]] = {HASH_A: (_peer(_PEER),)}
    fake_time, observability = FakeTime(), ObservabilityOverFakes()
    client = FakeDownloadClient(listed=[(status(HASH_A),)] * 3)
    source_client = FakeSourceClient(readings=readings, fake_time=fake_time)
    cycle = _real_cycle(real_catalog, client, source_client, observability, fake_time)
    await cycle.run(NODE)
    fake_time.advance(timedelta(hours=13))
    readings[HASH_A] = (_peer(_PEER, SourceRole.UNDETERMINED),)
    await cycle.run(NODE)
    fake_time.advance(timedelta(seconds=30))
    readings[HASH_A] = (_peer(_PEER),)
    await cycle.run(NODE)
    # The third round starts 13 h 30 s after the first, plus the 1 s each earlier read took.
    assert _alerts(observability) == [
        _alert(_PEER, "peer", timedelta(hours=13, seconds=32), HASH_A)
    ]
