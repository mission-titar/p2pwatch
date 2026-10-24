"""Repeats the download cycle until shutdown."""

import asyncio
from contextlib import suppress
from datetime import timedelta

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.ports.driven.waker import Waker
from p2pwatch.application.steps.download_cycle import DownloadCycle
from p2pwatch.domain.wake_subject import WakeSubject


class DownloadLoop:
    """The download cycle repeated until shutdown, between a poll interval or a wake."""

    def __init__(
        self,
        *,
        download_cycle: DownloadCycle,
        poll_interval_seconds: float,
        monotonic_clock: MonotonicClock,
        waker: Waker,
        run_state_reader: RunStateReader,
    ) -> None:
        self._download_cycle = download_cycle
        self._poll_interval = timedelta(seconds=poll_interval_seconds)
        self._monotonic_clock = monotonic_clock
        self._waker = waker
        self._run_state_reader = run_state_reader

    async def run(self, node_id: str) -> None:
        """Repeats the cycle then waits (poll/wake) until shutdown (DECISION D12).

        Launched by ``CrawlerLifecycle`` through ``LoopSupervisor``; cancellation (shutdown) lands
        at the next ``await`` (a poll or the sleep/wake wait), never mid DB write.
        """
        while not self._run_state_reader.is_shutdown_requested():
            await self._download_cycle.run(node_id)
            if self._run_state_reader.is_shutdown_requested():
                break
            await self._sleep_or_wake()

    async def _sleep_or_wake(self) -> None:
        """Waits ``poll_interval`` OR the ``download`` wake, whichever comes FIRST (spec §5).

        ``asyncio.wait(FIRST_COMPLETED)`` then cancel the loser: a download decision's wake resumes
        the loop immediately; otherwise the fallback poll wakes it at the cadence.
        Shutdown cancellation lands HERE (an ``await``), never mid DB write (sync).
        """
        sleep_task = asyncio.ensure_future(self._monotonic_clock.sleep(self._poll_interval))
        wake_task = asyncio.ensure_future(self._waker.wait(WakeSubject.DOWNLOAD))
        try:
            await asyncio.wait({sleep_task, wake_task}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (sleep_task, wake_task):
                if not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
