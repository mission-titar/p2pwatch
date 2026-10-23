"""Repeats the download cycle until shutdown."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta

from p2pwatch.application.ports.driven.waker import Waker
from p2pwatch.application.steps.download_cycle import run_download_cycle
from p2pwatch.application.steps.download_deps import DownloadDeps
from p2pwatch.domain.wake_subject import WakeSubject


@dataclass
class DownloadLoopDeps(DownloadDeps):
    """``DownloadDeps`` + what it takes to REPEAT (waker, shutdown) - DECISION D12."""

    waker: Waker
    shutdown: asyncio.Event


async def _sleep_or_wake(deps: DownloadLoopDeps) -> None:
    """Waits ``poll_interval`` OR the ``download`` wake, whichever comes FIRST (spec §5).

    ``asyncio.wait(FIRST_COMPLETED)`` then cancel the loser: a download decision's wake resumes the
    loop immediately; otherwise the fallback poll wakes it at the cadence.
    Shutdown cancellation lands HERE (an ``await``), never mid DB write (sync).
    """
    poll_interval = timedelta(seconds=deps.poll_interval_seconds)
    sleep_task = asyncio.ensure_future(deps.monotonic_clock.sleep(poll_interval))
    wake_task = asyncio.ensure_future(deps.waker.wait(WakeSubject.DOWNLOAD))
    try:
        await asyncio.wait({sleep_task, wake_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (sleep_task, wake_task):
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task


async def download_loop(deps: DownloadLoopDeps, node_id: str) -> None:
    """Repeats ``run_download_cycle`` then waits (poll/wake) until shutdown (DECISION D12).

    Launched by ``CrawlerLifecycle`` through ``supervise_loops``; cancellation (shutdown) lands
    at the next ``await`` (a poll or the sleep/wake wait), never mid DB write.
    """
    while not deps.shutdown.is_set():
        await run_download_cycle(deps, node_id)
        if deps.shutdown.is_set():
            break
        await _sleep_or_wake(deps)
