"""One task per (client, channel, keyword), each searching again as soon as it may: the client
paces its own starts, the core sets no interval (spec stage 2, D4).

The backoff is saved after a search whenever it differs from what was last saved (D7).
"""

import asyncio
from collections.abc import Sequence
from datetime import timedelta

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.steps.backoff_saver import BackoffSaver
from p2pwatch.application.steps.search_worker import SearchTask, SearchWorker


class SearchTaskRunner:
    """Runs each task the composition enumerated with the worker that searches it."""

    def __init__(
        self,
        *,
        tasks: Sequence[tuple[SearchWorker, SearchTask]],
        backoff_saver: BackoffSaver,
        monotonic_clock: MonotonicClock,
    ) -> None:
        self._tasks = tasks
        self._backoff_saver = backoff_saver
        self._monotonic_clock = monotonic_clock

    async def run(self) -> None:
        """Runs every task until cancelled."""
        async with asyncio.TaskGroup() as group:
            for worker, task in self._tasks:
                group.create_task(self._search_forever(worker, task=task))

    async def _search_forever(self, worker: SearchWorker, *, task: SearchTask) -> None:
        while True:
            wait = worker.time_until_ready(task.channel)
            if wait > timedelta(0):
                await self._monotonic_clock.sleep(wait)
                continue
            with self._backoff_saver.saving():
                await worker.run_task(task)
            # A yield that reads no clock: a search that never suspends must not starve the loop.
            await asyncio.sleep(0)  # noqa: TID251
