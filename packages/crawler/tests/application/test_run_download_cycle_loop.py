import asyncio
from datetime import timedelta

import pytest

from p2pwatch.application.run_download_cycle import (
    DOWNLOAD_WAKE_SUBJECT,
    DownloadLoopDeps,
    download_loop,
)
from p2pwatch.ports.driven.catalog_repository import DownloadCandidate
from p2pwatch.ports.driven.clock import MonotonicInstant
from p2pwatch_testing.application.download_fakes import (
    FakeCatalogReads,
    FakeDiskSpace,
    FakeDownloadClient,
    FakeDownloadRepo,
    FakeSourceRepo,
)
from p2pwatch_testing.application.fakes import FakeLogger, FakeTime, RecordingTelemetry

_NODE = "n1"


class RecordingWakeHub:
    """Wake hub that records + wakes (the test IS the producer)."""

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
    wake_hub: RecordingWakeHub,
    shutdown: asyncio.Event,
    poll_interval: float = 30.0,
    fake_time: FakeTime | None = None,
) -> DownloadLoopDeps:
    client = FakeDownloadClient()
    fake_time = fake_time or FakeTime()
    return DownloadLoopDeps(
        download_client=client,
        source_client=client,
        downloads=FakeDownloadRepo(),
        sources=FakeSourceRepo(),
        catalog=FakeCatalogReads(),
        targets=(),
        disk=FakeDiskSpace(1_000_000),
        min_free_bytes=0,
        lost_after=timedelta(days=1),
        reappeared_after=timedelta(hours=12),
        sources_interval=timedelta(minutes=5),
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        telemetry=RecordingTelemetry(),
        logger=FakeLogger(),
        wake_hub=wake_hub,
        poll_interval_seconds=poll_interval,
        shutdown=shutdown,
    )


@pytest.mark.asyncio
async def test_loop_stops_when_shutdown_is_set_before_start() -> None:
    shutdown = asyncio.Event()
    shutdown.set()
    deps = _loop_deps(wake_hub=RecordingWakeHub(), shutdown=shutdown)
    await asyncio.wait_for(download_loop(deps, _NODE), timeout=1.0)  # runs no cycle


@pytest.mark.asyncio
async def test_loop_runs_a_cycle_then_sleeps_then_stops() -> None:
    shutdown = asyncio.Event()
    wake_hub = RecordingWakeHub()
    fake_time = FakeTime()
    deps = _loop_deps(wake_hub=wake_hub, shutdown=shutdown, fake_time=fake_time)

    async def stop_after_first_sleep() -> None:
        # let one cycle + the wait entry happen, then request shutdown and wake the loop.
        while not fake_time.sleeps:
            await asyncio.sleep(0)
        shutdown.set()
        wake_hub.wake(DOWNLOAD_WAKE_SUBJECT)

    await asyncio.gather(
        asyncio.wait_for(download_loop(deps, _NODE), timeout=2.0), stop_after_first_sleep()
    )
    assert fake_time.sleeps[0] == timedelta(seconds=30)  # one poll interval


@pytest.mark.asyncio
async def test_nudge_wakes_the_loop_before_poll_expires() -> None:
    shutdown = asyncio.Event()
    wake_hub = RecordingWakeHub()
    deps = _loop_deps(wake_hub=wake_hub, shutdown=shutdown, poll_interval=999.0)

    async def wake_then_stop() -> None:
        while DOWNLOAD_WAKE_SUBJECT not in wake_hub.waited:
            await asyncio.sleep(0)
        shutdown.set()
        wake_hub.wake(DOWNLOAD_WAKE_SUBJECT)  # wakes the wait before the 999 s poll

    await asyncio.gather(
        asyncio.wait_for(download_loop(deps, _NODE), timeout=2.0), wake_then_stop()
    )
    assert DOWNLOAD_WAKE_SUBJECT in wake_hub.waited


class _ShutdownDuringCycleCatalog(FakeCatalogReads):
    """DownloadCatalogReader setting ``shutdown`` on the 1st ``download_candidates``, mid-cycle."""

    def __init__(self, shutdown: asyncio.Event) -> None:
        super().__init__()
        self._shutdown = shutdown

    def download_candidates(self) -> tuple[DownloadCandidate, ...]:
        self._shutdown.set()
        return ()


@pytest.mark.asyncio
async def test_loop_breaks_when_shutdown_is_set_during_the_cycle() -> None:
    # the `if deps.shutdown.is_set(): break` AFTER the cycle: shutdown set DURING the cycle
    # (by the catalog) → break without calling _sleep_or_wake (no sleep recorded).
    shutdown = asyncio.Event()
    fake_time = FakeTime()
    deps = _loop_deps(wake_hub=RecordingWakeHub(), shutdown=shutdown, fake_time=fake_time)
    deps.catalog = _ShutdownDuringCycleCatalog(shutdown)
    await asyncio.wait_for(download_loop(deps, _NODE), timeout=1.0)
    assert fake_time.sleeps == []  # break before any sleep/wake


class _BlockingMonotonicClock:
    """Monotonic clock whose ``sleep`` BLOCKS for good (the wake must win and cancel the sleep).

    Structurally satisfies ``MonotonicClock``: ``now`` (unused by the loop) + ``sleep`` that
    never resolves → the wake wins and the pending sleep_task is cancelled.
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
    wake_hub = RecordingWakeHub()
    deps = _loop_deps(wake_hub=wake_hub, shutdown=shutdown)
    deps.monotonic_clock = _BlockingMonotonicClock()
    wake_hub.wake(DOWNLOAD_WAKE_SUBJECT)  # wake already armed → wait() returns at once

    async def stop_when_waited() -> None:
        while DOWNLOAD_WAKE_SUBJECT not in wake_hub.waited:
            await asyncio.sleep(0)
        shutdown.set()
        wake_hub.wake(DOWNLOAD_WAKE_SUBJECT)

    await asyncio.gather(
        asyncio.wait_for(download_loop(deps, _NODE), timeout=2.0), stop_when_waited()
    )
    assert DOWNLOAD_WAKE_SUBJECT in wake_hub.waited


@pytest.mark.asyncio
async def test_loop_cancelled_mid_wait_propagates_cleanly() -> None:
    # The real shutdown trigger in prod: CrawlerApp's TaskGroup cancels the loop task WHILE
    # it sleeps in _sleep_or_wake. _BlockingMonotonicClock + no wake → the loop parks on
    # asyncio.wait; the cancellation lands there, the finally cancels the children, and the
    # CancelledError propagates cleanly (the loop stops, with no leaked task).
    shutdown = asyncio.Event()  # NEVER set: only cancellation stops the loop
    wake_hub = RecordingWakeHub()
    deps = _loop_deps(wake_hub=wake_hub, shutdown=shutdown)
    deps.monotonic_clock = _BlockingMonotonicClock()
    task = asyncio.ensure_future(download_loop(deps, _NODE))
    # wait until the loop is parked in _sleep_or_wake (wake_task has called wait())
    while DOWNLOAD_WAKE_SUBJECT not in wake_hub.waited:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
