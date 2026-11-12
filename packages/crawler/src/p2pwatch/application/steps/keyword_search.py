"""One keyword's searches on one channel of one client, a work: each turn searches again as soon
as it may, the client pacing its own starts, the core setting no interval (spec stage 2, D4); each
search's declared outcome recorded on its channel (spec v5 lot 4, D10)."""

from datetime import timedelta

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.steps.backoff_saver import BackoffSaver
from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.search_worker import SearchWorker
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.client_errors import SearchFailedError
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.outcome import Outcome
from p2pwatch.domain.identifiers import Channel, Keyword
from p2pwatch.domain.search.searches_failed import SEARCHES


class KeywordSearch(Work):
    """One keyword on one channel, searched by its client's worker, the backoff saved after each
    turn."""

    def __init__(
        self,
        *,
        keyword: Keyword,
        channel: Channel,
        search_worker: SearchWorker,
        backoff_saver: BackoffSaver,
        monotonic_clock: MonotonicClock,
        health_recorder: HealthRecorder,
        channel_component: Component,
    ) -> None:
        self._keyword = keyword
        self._channel = channel
        self._search_worker = search_worker
        self._backoff_saver = backoff_saver
        self._monotonic_clock = monotonic_clock
        self._health_recorder = health_recorder
        self._channel_component = channel_component

    def __str__(self) -> str:
        return f"search '{self._keyword}' {self._search_worker.client_name} {self._channel}"

    async def wait_for_next_turn(self) -> None:
        """Waits until neither the client nor the channel is backed off, a backoff resumed at the
        start or set by another work while it waited included."""
        while (wait := self._search_worker.time_until_ready(self._channel)) > timedelta(0):
            await self._monotonic_clock.sleep(wait)

    async def run_once(self) -> None:
        """Searches the keyword once, saves the backoff if the search changed it, then records a
        success or a refused search on the channel; any other failure records nothing there."""
        try:
            with self._backoff_saver.saving():
                await self._search_worker.search(self._keyword, channel=self._channel)
        except SearchFailedError as refusal:
            # An unreachable client or a refused password says nothing of the network's answer.
            await self._record(Outcome.declared(refusal))
            raise
        await self._record(Outcome.success())

    async def _record(self, outcome: Outcome) -> None:
        await self._health_recorder.record(outcome, on=self._channel_component, by=SEARCHES)
