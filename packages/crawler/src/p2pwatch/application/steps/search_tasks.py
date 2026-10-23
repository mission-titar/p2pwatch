"""One task per (client, channel, keyword), each searching again as soon as it may: the client
paces its own starts, the core sets no interval (spec stage 2, D4).

The backoff is saved after a search whenever it differs from what was last saved (D7).
"""

import asyncio
from collections.abc import Sequence
from datetime import timedelta

from p2pwatch.application.ports.driven.backoff_state_writer import BackoffStateWriter
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.steps.search_worker import BackoffRegistry, SearchTask, SearchWorker
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from p2pwatch.domain.search.keywords import dedupe_keywords
from p2pwatch.domain.store_error import StoreError


class SearchTaskRunner:
    """The backoff last saved is the state the tasks share."""

    def __init__(
        self,
        *,
        workers: Sequence[SearchWorker],
        keywords: Sequence[str],
        resumed: asyncio.Event,
        backoff: BackoffRegistry,
        backoff_state_writer: BackoffStateWriter,
        monotonic_clock: MonotonicClock,
        logger: Logger,
    ) -> None:
        self._workers = workers
        self._keywords = keywords
        self._resumed = resumed
        self._backoff = backoff
        self._backoff_state_writer = backoff_state_writer
        self._monotonic_clock = monotonic_clock
        self._logger = logger
        self._saved: dict[BackoffKey, BackoffState] = {}

    async def run(self, node_id: str) -> None:
        """Runs every task until cancelled, recording what they find under ``node_id``."""
        # Taken here, once the lifecycle resumed the backoff, so no search rewrites what it read.
        self._saved = self._backoff.snapshot()
        texts = [keyword.text for keyword in dedupe_keywords(self._keywords)]
        async with asyncio.TaskGroup() as group:
            for worker in self._workers:
                for channel in worker.channels:
                    for text in texts:
                        group.create_task(
                            self._search_forever(worker, SearchTask(text, channel), node_id)
                        )

    async def _search_forever(self, worker: SearchWorker, task: SearchTask, node_id: str) -> None:
        while True:
            await self._resumed.wait()
            wait = worker.time_until_ready(task.channel)
            if wait > timedelta(0):
                await self._monotonic_clock.sleep(wait)
                continue
            await worker.run_task(task, node_id)
            self._save()
            # A yield that reads no clock: a search that never suspends must not starve the loop.
            await asyncio.sleep(0)  # noqa: TID251

    def _save(self) -> None:
        current = self._backoff.snapshot()
        if current == self._saved:
            return
        try:
            self._backoff_state_writer.set_backoff_states(current)
        except StoreError as error:
            self._logger.error("backoff not saved (%s): retried after the next search", error)
            return
        self._saved = current
