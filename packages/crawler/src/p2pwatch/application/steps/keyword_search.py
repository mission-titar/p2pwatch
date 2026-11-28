"""``KeywordSearch``: one keyword searched on one channel of one client, such as "keroro" on Kad,
again as soon as the channel may; the client spaces its own starts, the core sets no interval."""

from collections.abc import Iterable, Sequence
from datetime import timedelta
from typing import Protocol

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.steps.backoff_saver import BackoffSaver
from p2pwatch.application.steps.function_progress import FunctionProgress
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.search_worker import SearchWorker
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.domain.client_errors import SearchFailedError
from p2pwatch.domain.crawler_function import CrawlerFunction
from p2pwatch.domain.health.external_dependency import ExternalDependency
from p2pwatch.domain.identifiers import Channel, Keyword
from p2pwatch.domain.search.keywords import dedupe_keywords
from p2pwatch.domain.status_reading import SEARCHES_FAILED
from p2pwatch.domain.watched_function import WatchedFunction


# The time limit of the search of ``keyword`` on ``channel``.
class SearchTimeLimitOf(Protocol):
    def __call__(self, keyword: Keyword, /, *, channel: Channel) -> timedelta: ...


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
        node_health: NodeHealth,
        channel_dependency: ExternalDependency,
        function_progress: FunctionProgress,
    ) -> None:
        self._keyword = keyword
        self._channel = channel
        self._search_worker = search_worker
        self._backoff_saver = backoff_saver
        self._monotonic_clock = monotonic_clock
        self._node_health = node_health
        self._channel_dependency = channel_dependency
        self._function_progress = function_progress
        self._function = WatchedFunction(client_name=search_worker.client_name, channel=channel)

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
        search included, records on the channel whether the network refused the search, and the
        crawl's progress on the channel once the search completed."""
        # aMule unreachable or refusing our password records nothing: the network said nothing.
        try:
            with self._backoff_saver.saving():
                await self._search_worker.search(self._keyword, channel=self._channel)
        except SearchFailedError:
            await self._record_searches_failed(detected=True)
            raise
        await self._record_searches_failed(detected=False)
        self._function_progress.record_progress(self._function)

    async def _record_searches_failed(self, *, detected: bool) -> None:
        await self._node_health.record(
            on=self._channel_dependency, rule=SEARCHES_FAILED, detected=detected
        )


def keyword_searches(
    *,
    search_workers: Sequence[SearchWorker],
    keywords: Sequence[str],
    backoff_saver: BackoffSaver,
    monotonic_clock: MonotonicClock,
    time_limit_of: SearchTimeLimitOf,
    node_health: NodeHealth,
    channel_dependencies: Iterable[ExternalDependency],
    function_progress: FunctionProgress,
) -> list[SupervisedWork]:
    """One search per client, channel and keyword of the config, with its time limit, a keyword
    listed twice searched once and an empty one never; each records its refusals on its channel,
    and its progress in ``function_progress``."""
    each_keyword_once = dedupe_keywords(keywords)
    channel_of = {
        (channel.client_name, channel.channel): channel for channel in channel_dependencies
    }
    return [
        SupervisedWork(
            work=KeywordSearch(
                keyword=keyword,
                channel=channel,
                search_worker=search_worker,
                backoff_saver=backoff_saver,
                monotonic_clock=monotonic_clock,
                node_health=node_health,
                channel_dependency=channel_of[search_worker.client_name, channel],
                function_progress=function_progress,
            ),
            time_limit=time_limit_of(keyword, channel=channel),
            function=CrawlerFunction.CRAWL,
        )
        for search_worker in search_workers
        for channel in search_worker.channels
        for keyword in each_keyword_once
    ]
