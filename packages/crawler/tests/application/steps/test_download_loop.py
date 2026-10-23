import asyncio
from datetime import timedelta

import pytest

from p2pwatch.application.steps.download_loop import (
    DOWNLOAD_WAKE_SUBJECT,
    DownloadLoopDeps,
    download_loop,
)
from tests.fakes.adapters.driven.fake_blocking_monotonic_clock import FakeBlockingMonotonicClock
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_event_emitter import FakeEventEmitter
from tests.fakes.adapters.driven.fake_free_space_meter import FakeFreeSpaceMeter
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
from tests.fakes.adapters.driven.fake_shutdown_during_cycle_decision_reader import (
    FakeShutdownDuringCycleDecisionReader,
)
from tests.fakes.adapters.driven.fake_source_client import FakeSourceClient
from tests.fakes.adapters.driven.fake_source_point_store import FakeSourcePointStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore
from tests.fakes.adapters.driven.fake_waker import FakeWaker

_NODE = "n1"


def _loop_deps(
    *,
    waker: FakeWaker,
    shutdown: asyncio.Event,
    poll_interval: float = 30.0,
    fake_time: FakeTime | None = None,
) -> DownloadLoopDeps:
    downloads = FakeTrackedDownloadStore()
    sources = FakeSourcePointStore()
    fake_time = fake_time or FakeTime()
    return DownloadLoopDeps(
        download_client=FakeDownloadClient(),
        source_client=FakeSourceClient(),
        tracked_download_writer=downloads,
        tracked_download_reader=downloads,
        source_point_writer=sources,
        source_point_reader=sources,
        decision_reader=FakeDecisionReader(),
        observation_reader=FakeObservationReader(),
        targets=(),
        free_space_meter=FakeFreeSpaceMeter(1_000_000),
        min_free_bytes=0,
        lost_after=timedelta(days=1),
        reappeared_after=timedelta(hours=12),
        sources_interval=timedelta(minutes=5),
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        event_emitter=FakeEventEmitter(),
        logger=FakeLogger(),
        waker=waker,
        poll_interval_seconds=poll_interval,
        shutdown=shutdown,
    )


@pytest.mark.asyncio
async def test_loop_stops_when_shutdown_is_set_before_start() -> None:
    shutdown = asyncio.Event()
    shutdown.set()
    deps = _loop_deps(waker=FakeWaker(), shutdown=shutdown)
    await asyncio.wait_for(download_loop(deps, _NODE), timeout=1.0)  # runs no cycle


@pytest.mark.asyncio
async def test_loop_runs_a_cycle_then_sleeps_then_stops() -> None:
    shutdown = asyncio.Event()
    waker = FakeWaker()
    fake_time = FakeTime()
    deps = _loop_deps(waker=waker, shutdown=shutdown, fake_time=fake_time)

    async def stop_after_first_sleep() -> None:
        # let one cycle + the wait entry happen, then request shutdown and wake the loop.
        while not fake_time.sleeps:
            await asyncio.sleep(0)
        shutdown.set()
        waker.wake(DOWNLOAD_WAKE_SUBJECT)

    await asyncio.gather(
        asyncio.wait_for(download_loop(deps, _NODE), timeout=2.0), stop_after_first_sleep()
    )
    assert fake_time.sleeps[0] == timedelta(seconds=30)  # one poll interval


@pytest.mark.asyncio
async def test_nudge_wakes_the_loop_before_poll_expires() -> None:
    shutdown = asyncio.Event()
    waker = FakeWaker()
    deps = _loop_deps(waker=waker, shutdown=shutdown, poll_interval=999.0)

    async def wake_then_stop() -> None:
        while DOWNLOAD_WAKE_SUBJECT not in waker.waited_subjects:
            await asyncio.sleep(0)
        shutdown.set()
        waker.wake(DOWNLOAD_WAKE_SUBJECT)  # wakes the wait before the 999 s poll

    await asyncio.gather(
        asyncio.wait_for(download_loop(deps, _NODE), timeout=2.0), wake_then_stop()
    )
    assert DOWNLOAD_WAKE_SUBJECT in waker.waited_subjects


@pytest.mark.asyncio
async def test_loop_breaks_when_shutdown_is_set_during_the_cycle() -> None:
    # the `if deps.shutdown.is_set(): break` AFTER the cycle: shutdown set DURING the cycle
    # (by the catalog) → break without calling _sleep_or_wake (no sleep recorded).
    shutdown = asyncio.Event()
    fake_time = FakeTime()
    deps = _loop_deps(waker=FakeWaker(), shutdown=shutdown, fake_time=fake_time)
    deps.decision_reader = FakeShutdownDuringCycleDecisionReader(shutdown)
    await asyncio.wait_for(download_loop(deps, _NODE), timeout=1.0)
    assert fake_time.sleeps == []  # break before any sleep/wake


@pytest.mark.asyncio
async def test_nudge_wins_and_cancels_the_pending_sleep() -> None:
    # _sleep_or_wake: wake PRE-armed → the `if not task.done(): task.cancel()` branch is
    # exercised on the still-running sleep_task (the FakeBlockingMonotonicClock never resolves it).
    shutdown = asyncio.Event()
    waker = FakeWaker()
    deps = _loop_deps(waker=waker, shutdown=shutdown)
    deps.monotonic_clock = FakeBlockingMonotonicClock()
    waker.wake(DOWNLOAD_WAKE_SUBJECT)  # wake already armed → wait() returns at once

    async def stop_when_waited() -> None:
        while DOWNLOAD_WAKE_SUBJECT not in waker.waited_subjects:
            await asyncio.sleep(0)
        shutdown.set()
        waker.wake(DOWNLOAD_WAKE_SUBJECT)

    await asyncio.gather(
        asyncio.wait_for(download_loop(deps, _NODE), timeout=2.0), stop_when_waited()
    )
    assert DOWNLOAD_WAKE_SUBJECT in waker.waited_subjects


@pytest.mark.asyncio
async def test_loop_cancelled_mid_wait_propagates_cleanly() -> None:
    # The real shutdown trigger in prod: CrawlerComposition's TaskGroup cancels the loop task WHILE
    # it sleeps in _sleep_or_wake. FakeBlockingMonotonicClock + no wake → the loop parks on
    # asyncio.wait; the cancellation lands there, the finally cancels the children, and the
    # CancelledError propagates cleanly (the loop stops, with no leaked task).
    shutdown = asyncio.Event()  # NEVER set: only cancellation stops the loop
    waker = FakeWaker()
    deps = _loop_deps(waker=waker, shutdown=shutdown)
    deps.monotonic_clock = FakeBlockingMonotonicClock()
    task = asyncio.ensure_future(download_loop(deps, _NODE))
    # wait until the loop is parked in _sleep_or_wake (wake_task has called wait())
    while DOWNLOAD_WAKE_SUBJECT not in waker.waited_subjects:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
