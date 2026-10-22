import asyncio
from datetime import timedelta

import pytest

from p2pwatch.application.run_download_cycle import (
    DOWNLOAD_WAKE_SUBJECT,
    DownloadLoopDeps,
    download_loop,
)
from p2pwatch.domain.download.candidate import DownloadCandidate
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.ports.driven.clock import MonotonicClock
from p2pwatch.ports.driven.waker import Waker
from tests.fakes.application.download_fakes import (
    FakeCatalogReader,
    FakeDownloadClient,
    FakeDownloadStore,
    FakeFreeSpaceMeter,
    FakeSourcePointStore,
)
from tests.fakes.application.fakes import FakeEventEmitter, FakeLogger, FakeTime

_NODE = "n1"


class _RecordingWaker(Waker):
    """Waker that records + wakes (the test IS the producer)."""

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}
        self.waited: list[str] = []

    def wake(self, subject: str) -> None:
        self._events.setdefault(subject, asyncio.Event()).set()

    async def wait(self, subject: str) -> None:
        self.waited.append(subject)
        event = self._events.setdefault(subject, asyncio.Event())
        await event.wait()
        event.clear()


def _loop_deps(
    *,
    waker: _RecordingWaker,
    shutdown: asyncio.Event,
    poll_interval: float = 30.0,
    fake_time: FakeTime | None = None,
) -> DownloadLoopDeps:
    client = FakeDownloadClient()
    downloads = FakeDownloadStore()
    sources = FakeSourcePointStore()
    catalog = FakeCatalogReader()
    fake_time = fake_time or FakeTime()
    return DownloadLoopDeps(
        download_client=client,
        source_client=client,
        download_writer=downloads,
        download_reader=downloads,
        source_point_writer=sources,
        source_point_reader=sources,
        decision_reader=catalog,
        observation_reader=catalog,
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
    deps = _loop_deps(waker=_RecordingWaker(), shutdown=shutdown)
    await asyncio.wait_for(download_loop(deps, _NODE), timeout=1.0)  # runs no cycle


@pytest.mark.asyncio
async def test_loop_runs_a_cycle_then_sleeps_then_stops() -> None:
    shutdown = asyncio.Event()
    waker = _RecordingWaker()
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
    waker = _RecordingWaker()
    deps = _loop_deps(waker=waker, shutdown=shutdown, poll_interval=999.0)

    async def wake_then_stop() -> None:
        while DOWNLOAD_WAKE_SUBJECT not in waker.waited:
            await asyncio.sleep(0)
        shutdown.set()
        waker.wake(DOWNLOAD_WAKE_SUBJECT)  # wakes the wait before the 999 s poll

    await asyncio.gather(
        asyncio.wait_for(download_loop(deps, _NODE), timeout=2.0), wake_then_stop()
    )
    assert DOWNLOAD_WAKE_SUBJECT in waker.waited


class _ShutdownDuringCycleCatalog(FakeCatalogReader):
    """Sets ``shutdown`` on the 1st ``read_download_candidates``, mid-cycle."""

    def __init__(self, shutdown: asyncio.Event) -> None:
        super().__init__()
        self._shutdown = shutdown

    def read_download_candidates(self) -> tuple[DownloadCandidate, ...]:
        self._shutdown.set()
        return ()


@pytest.mark.asyncio
async def test_loop_breaks_when_shutdown_is_set_during_the_cycle() -> None:
    # the `if deps.shutdown.is_set(): break` AFTER the cycle: shutdown set DURING the cycle
    # (by the catalog) → break without calling _sleep_or_wake (no sleep recorded).
    shutdown = asyncio.Event()
    fake_time = FakeTime()
    deps = _loop_deps(waker=_RecordingWaker(), shutdown=shutdown, fake_time=fake_time)
    deps.decision_reader = _ShutdownDuringCycleCatalog(shutdown)
    await asyncio.wait_for(download_loop(deps, _NODE), timeout=1.0)
    assert fake_time.sleeps == []  # break before any sleep/wake


class _BlockingMonotonicClock(MonotonicClock):
    """Monotonic clock whose ``sleep`` BLOCKS for good (the wake must win and cancel the sleep).

    ``now`` is unused by the loop; ``sleep`` never resolves, so the pending sleep_task is cancelled.
    """

    def now(self) -> MonotonicInstant:
        return MonotonicInstant(0)

    async def sleep(self, duration: timedelta) -> None:
        await asyncio.Event().wait()  # NEVER resolves


@pytest.mark.asyncio
async def test_nudge_wins_and_cancels_the_pending_sleep() -> None:
    # _sleep_or_wake: wake PRE-armed → the `if not task.done(): task.cancel()` branch is
    # exercised on the still-running sleep_task (the _BlockingMonotonicClock never resolves it).
    shutdown = asyncio.Event()
    waker = _RecordingWaker()
    deps = _loop_deps(waker=waker, shutdown=shutdown)
    deps.monotonic_clock = _BlockingMonotonicClock()
    waker.wake(DOWNLOAD_WAKE_SUBJECT)  # wake already armed → wait() returns at once

    async def stop_when_waited() -> None:
        while DOWNLOAD_WAKE_SUBJECT not in waker.waited:
            await asyncio.sleep(0)
        shutdown.set()
        waker.wake(DOWNLOAD_WAKE_SUBJECT)

    await asyncio.gather(
        asyncio.wait_for(download_loop(deps, _NODE), timeout=2.0), stop_when_waited()
    )
    assert DOWNLOAD_WAKE_SUBJECT in waker.waited


@pytest.mark.asyncio
async def test_loop_cancelled_mid_wait_propagates_cleanly() -> None:
    # The real shutdown trigger in prod: CrawlerApp's TaskGroup cancels the loop task WHILE
    # it sleeps in _sleep_or_wake. _BlockingMonotonicClock + no wake → the loop parks on
    # asyncio.wait; the cancellation lands there, the finally cancels the children, and the
    # CancelledError propagates cleanly (the loop stops, with no leaked task).
    shutdown = asyncio.Event()  # NEVER set: only cancellation stops the loop
    waker = _RecordingWaker()
    deps = _loop_deps(waker=waker, shutdown=shutdown)
    deps.monotonic_clock = _BlockingMonotonicClock()
    task = asyncio.ensure_future(download_loop(deps, _NODE))
    # wait until the loop is parked in _sleep_or_wake (wake_task has called wait())
    while DOWNLOAD_WAKE_SUBJECT not in waker.waited:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
