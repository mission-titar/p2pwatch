"""One task per (client, channel, keyword), each searching again as soon as it may: the client
paces its own starts, the core sets no interval (spec stage 2, D4).

The backoff is saved after a search whenever it differs from what was last saved (D7).
"""

import asyncio
import logging
from collections.abc import Sequence
from datetime import timedelta

from p2pwatch.application.search_worker import BackoffRegistry, SearchTask, SearchWorker
from p2pwatch.domain.search.keywords import dedupe_keywords
from p2pwatch.ports.backoff_state_repository import BackoffStateRepository
from p2pwatch.ports.clock import MonotonicClock
from p2pwatch.ports.repository_errors import RepositoryError

_logger = logging.getLogger("p2pwatch.application.search_tasks")


class SearchTaskRunner:
    """The backoff last saved is the state the tasks share."""

    def __init__(
        self,
        *,
        workers: Sequence[SearchWorker],
        keywords: Sequence[str],
        resumed: asyncio.Event,
        backoff: BackoffRegistry,
        backoff_states: BackoffStateRepository,
        monotonic_clock: MonotonicClock,
    ) -> None:
        self._workers = workers
        self._keywords = keywords
        self._resumed = resumed
        self._backoff = backoff
        self._backoff_states = backoff_states
        self._monotonic_clock = monotonic_clock
        self._saved = backoff.snapshot()

    async def run(self) -> None:
        """Runs every task until cancelled."""
        texts = [keyword.text for keyword in dedupe_keywords(self._keywords)]
        async with asyncio.TaskGroup() as group:
            for worker in self._workers:
                for channel in worker.channels:
                    for text in texts:
                        group.create_task(self._search_forever(worker, SearchTask(text, channel)))

    async def _search_forever(self, worker: SearchWorker, task: SearchTask) -> None:
        while True:
            await self._resumed.wait()
            wait = worker.time_until_ready(task.channel)
            if wait > timedelta(0):
                await self._monotonic_clock.sleep(wait)
                continue
            await worker.run_task(task)
            self._save()
            # A yield that reads no clock: a search that never suspends must not starve the loop.
            await asyncio.sleep(0)  # noqa: TID251

    def _save(self) -> None:
        current = self._backoff.snapshot()
        if current == self._saved:
            return
        try:
            self._backoff_states.save_backoff_states(current)
        except RepositoryError as error:
            _logger.error("backoff not saved (%s): retried after the next search", error)
            return
        self._saved = current
