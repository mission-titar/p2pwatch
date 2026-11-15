"""One task per (client, channel, keyword), each searching again as soon as it may: the client
paces its own starts, the core sets no interval (spec stage 2, D4)."""

import asyncio
from collections.abc import Sequence
from datetime import timedelta

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.steps.backoff_saver import BackoffSaver
from p2pwatch.application.steps.search_worker import SearchTask, SearchWorker
from p2pwatch.domain.search.keywords import dedupe_keywords


class SearchTaskRunner:
    """Runs one task per client, channel and keyword, the backoff saved after each search."""

    def __init__(
        self,
        *,
        workers: Sequence[SearchWorker],
        keywords: Sequence[str],
        backoff_saver: BackoffSaver,
        monotonic_clock: MonotonicClock,
    ) -> None:
        self._workers = workers
        self._keywords = keywords
        self._backoff_saver = backoff_saver
        self._monotonic_clock = monotonic_clock

    async def run(self) -> None:
        """Runs every task until cancelled."""
        keywords = dedupe_keywords(self._keywords)
        async with asyncio.TaskGroup() as group:
            for worker in self._workers:
                for channel in worker.channels:
                    for keyword in keywords:
                        group.create_task(
                            self._search_forever(
                                worker, task=SearchTask(keyword=keyword, channel=channel)
                            )
                        )

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
