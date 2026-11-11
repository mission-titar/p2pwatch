"""One keyword's searches on one channel of one client, a work: each turn searches again as soon
as it may, the client pacing its own starts, the core setting no interval (spec stage 2, D4)."""

from datetime import timedelta

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.steps.backoff_saver import BackoffSaver
from p2pwatch.application.steps.search_worker import SearchWorker
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.identifiers import Channel, Keyword


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
    ) -> None:
        self._keyword = keyword
        self._channel = channel
        self._search_worker = search_worker
        self._backoff_saver = backoff_saver
        self._monotonic_clock = monotonic_clock

    async def wait_for_next_turn(self) -> None:
        """Waits until neither the client nor the channel is backed off, a backoff resumed at the
        start or set by another work while it waited included."""
        while (wait := self._search_worker.time_until_ready(self._channel)) > timedelta(0):
            await self._monotonic_clock.sleep(wait)

    async def run_once(self) -> None:
        """Searches the keyword once, then saves the backoff if the search changed it."""
        with self._backoff_saver.saving():
            await self._search_worker.search(self._keyword, channel=self._channel)
