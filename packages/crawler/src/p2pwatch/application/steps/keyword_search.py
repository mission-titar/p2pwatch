"""``KeywordSearch``: one keyword searched on one channel of one client, such as "keroro" on Kad,
again as soon as the channel may; the client spaces its own starts, the core sets no interval."""

from collections.abc import Sequence
from datetime import timedelta

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.steps.backoff_saver import BackoffSaver
from p2pwatch.application.steps.search_worker import SearchWorker
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.identifiers import Channel, Keyword
from p2pwatch.domain.search.keywords import dedupe_keywords


class KeywordSearch(Work):
    """Searches one keyword on one channel, such as "keroro" on Kad, each turn once neither the
    client nor the channel is backed off."""

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

    def __str__(self) -> str:
        return f"search '{self._keyword}' {self._search_worker.client_name} {self._channel}"

    async def wait_for_next_turn(self) -> None:
        """Waits until neither the client nor the channel is backed off, so a backoff the previous
        run saved delays the first search too."""
        # Checked again after each sleep: another search may have backed them off meanwhile.
        while (wait := self._search_worker.time_until_ready(self._channel)) > timedelta(0):
            await self._monotonic_clock.sleep(wait)

    async def run_once(self) -> None:
        """Searches the keyword once, then saves the backoff if the search changed it, a failed
        search included."""
        with self._backoff_saver.saving():
            await self._search_worker.search(self._keyword, channel=self._channel)


def keyword_searches(
    *,
    search_workers: Sequence[SearchWorker],
    keywords: Sequence[str],
    backoff_saver: BackoffSaver,
    monotonic_clock: MonotonicClock,
) -> list[KeywordSearch]:
    """One search per client, channel and keyword of the config, a keyword listed twice searched
    once and an empty one never."""
    each_keyword_once = dedupe_keywords(keywords)
    return [
        KeywordSearch(
            keyword=keyword,
            channel=channel,
            search_worker=search_worker,
            backoff_saver=backoff_saver,
            monotonic_clock=monotonic_clock,
        )
        for search_worker in search_workers
        for channel in search_worker.channels
        for keyword in each_keyword_once
    ]
