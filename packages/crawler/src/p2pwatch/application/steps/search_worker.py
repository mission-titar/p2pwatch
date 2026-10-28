"""One client's searches: a task's search, its observations recorded, and the backoff a failure
earns, per client when unreachable and per channel when refused (stage 2, D4 and D7)."""

from dataclasses import dataclass
from datetime import timedelta

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.search_client import SearchClient
from p2pwatch.application.steps.backoff_registry import BackoffRegistry
from p2pwatch.application.steps.cataloguer import Cataloguer
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.client_errors import ClientUnreachableError, SearchFailedError
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.events import (
    ClientUnreachable,
    SearchExecuted,
    SearchFailed,
)
from p2pwatch.domain.search.answer import SearchAnswer
from p2pwatch.domain.search.backoff import BackoffKey

# A ceiling, not a duration: above Kad's 45 s and an ed2k sweep, it guards a search never ending.
SEARCH_BUDGET_SECONDS = 120.0


@dataclass(frozen=True)
class SearchTask:
    """A unit of work: a keyword on a channel (spec §4)."""

    keyword: str
    channel: str


class SearchWorker:
    """Runs one client's search tasks; never closes the client, which composition owns.

    ``backoff`` is the registry every worker and the search tasks share.
    """

    def __init__(
        self,
        *,
        client_name: str,
        client: SearchClient,
        backoff: BackoffRegistry,
        cataloguer: Cataloguer,
        observability_dispatcher: ObservabilityDispatcher,
        logger: Logger,
    ) -> None:
        self._client_name = client_name
        self._client_backoff_key = BackoffKey(client_name, None)
        self._client = client
        self._backoff = backoff
        self._cataloguer = cataloguer
        self._observability_dispatcher = observability_dispatcher
        self._logger = logger

    @property
    def channels(self) -> tuple[str, ...]:
        """The channels its client declares."""
        return self._client.channels()

    def time_until_ready(self, channel: str) -> timedelta:
        """How long until neither the client nor ``channel`` is backed off."""
        return max(
            self._backoff.time_until_retry(self._client_backoff_key),
            self._backoff.time_until_retry(BackoffKey(self._client_name, channel)),
        )

    async def _record_observations(
        self, channel: str, answer: SearchAnswer, node_id: NodeId
    ) -> int:
        """Per-obs pipeline; returns the number of CHANGED verdicts (logging). A
        ``StoreError`` per obs is ABSORBED inside ``Cataloguer.catalog`` (spec §7)."""
        await self._observability_dispatcher.dispatch(
            SearchExecuted(
                self._client_name, channel, len(answer.reported_files), answer.skipped_result_count
            )
        )
        changed = 0
        for reported_file in answer.reported_files:
            if await self._cataloguer.catalog(reported_file, self._client_name, channel, node_id):
                changed += 1
        return changed

    async def run_task(self, task: SearchTask, node_id: NodeId) -> None:
        """One search, run once ``time_until_ready`` is zero. Never raises: backs off and logs."""
        channel_backoff_key = BackoffKey(self._client_name, task.channel)
        try:
            answer = await self._client.search(task.keyword, task.channel, SEARCH_BUDGET_SECONDS)
        except SearchFailedError as error:
            delay = self._backoff.record_failure(channel_backoff_key)
            self._logger.warning(
                "client %s channel %s failed (%s): backoff %.1fs",
                self._client_name,
                task.channel,
                error,
                delay.total_seconds(),
            )
            await self._observability_dispatcher.dispatch(
                SearchFailed(self._client_name, task.channel)
            )
            return
        except ClientUnreachableError as error:
            delay = self._backoff.record_failure(self._client_backoff_key)
            self._logger.warning(
                "client %s unreachable (%s), client down, backoff %.1fs",
                self._client_name,
                error,
                delay.total_seconds(),
            )
            await self._observability_dispatcher.dispatch(ClientUnreachable(self._client_name))
            return
        changed = await self._record_observations(task.channel, answer, node_id)
        self._backoff.reset(channel_backoff_key)
        self._backoff.reset(self._client_backoff_key)
        self._logger.info(
            "client %s: '%s'/%s → %d verdict(s) changed",
            self._client_name,
            task.keyword,
            task.channel,
            changed,
        )
