"""One client's searches: a keyword's search, its observations recorded, and the backoff a failure
earns, per client when unreachable and per channel when refused."""

from datetime import timedelta

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.search_client import SearchClient
from p2pwatch.application.steps.backoff_registry import BackoffRegistry
from p2pwatch.application.steps.cataloguer import Cataloguer
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.client_errors import ClientUnreachableError, SearchFailedError
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword
from p2pwatch.domain.observability.events import (
    ClientUnreachable,
    SearchExecuted,
    SearchFailed,
)
from p2pwatch.domain.search.answer import SearchAnswer
from p2pwatch.domain.search.backoff import BackoffKey

# A ceiling, not a duration: above Kad's 45 s and an ed2k sweep, it guards a search never ending.
SEARCH_BUDGET_SECONDS = 120.0


class SearchWorker:
    """Runs one client's searches; never closes the client, which composition owns.

    ``backoff`` is the registry every worker shares.
    """

    def __init__(
        self,
        *,
        client_name: ClientName,
        client: SearchClient,
        backoff: BackoffRegistry,
        cataloguer: Cataloguer,
        observability_dispatcher: ObservabilityDispatcher,
        logger: Logger,
    ) -> None:
        self._client_name = client_name
        self._client_backoff_key = BackoffKey(client_name=client_name, channel=None)
        self._client = client
        self._backoff = backoff
        self._cataloguer = cataloguer
        self._observability_dispatcher = observability_dispatcher
        self._logger = logger

    @property
    def client_name(self) -> ClientName:
        """The name of its client, such as ``amuled``."""
        return self._client_name

    @property
    def channels(self) -> tuple[Channel, ...]:
        """The channels its client declares."""
        return self._client.channels()

    def time_until_ready(self, channel: Channel) -> timedelta:
        """How long until neither the client nor ``channel`` is backed off."""
        return max(
            self._backoff.time_until_retry(self._client_backoff_key),
            self._backoff.time_until_retry(
                BackoffKey(client_name=self._client_name, channel=channel)
            ),
        )

    async def _record_observations(
        self, channel: Channel, *, answer: SearchAnswer
    ) -> list[int | None]:
        """Per-obs pipeline; returns each file's decision rows written, ``None`` for one a
        ``StoreError`` left unrecorded, ABSORBED inside ``Cataloguer.catalog``."""
        await self._observability_dispatcher.dispatch(
            SearchExecuted(
                client_name=self._client_name,
                channel=channel,
                observation_count=len(answer.reported_files),
                skipped_result_count=answer.skipped_result_count,
            )
        )
        return [
            await self._cataloguer.catalog(
                reported_file, client_name=self._client_name, channel=channel
            )
            for reported_file in answer.reported_files
        ]

    async def search(self, keyword: Keyword, *, channel: Channel) -> bool:
        """One search, run once ``time_until_ready`` is zero; returns whether it progressed, a file
        of its answer recorded or none in it. A refused search or an unreachable client raises
        once the backoff is set, the warning logged and the event dispatched."""
        channel_backoff_key = BackoffKey(client_name=self._client_name, channel=channel)
        try:
            answer = await self._client.search(
                keyword, channel=channel, budget_seconds=SEARCH_BUDGET_SECONDS
            )
        except SearchFailedError as error:
            delay = self._backoff.record_failure(channel_backoff_key)
            self._logger.warning(
                "client %s channel %s failed (%s): backoff %g s",
                self._client_name,
                channel,
                error,
                delay.total_seconds(),
            )
            await self._observability_dispatcher.dispatch(
                SearchFailed(client_name=self._client_name, channel=channel)
            )
            raise
        except ClientUnreachableError as error:
            delay = self._backoff.record_failure(self._client_backoff_key)
            self._logger.warning(
                "client %s unreachable (%s), client down, backoff %g s",
                self._client_name,
                error,
                delay.total_seconds(),
            )
            await self._observability_dispatcher.dispatch(
                ClientUnreachable(client_name=self._client_name)
            )
            raise
        written = await self._record_observations(channel, answer=answer)
        self._backoff.reset(channel_backoff_key)
        self._backoff.reset(self._client_backoff_key)
        self._logger.info(
            "client %s: '%s'/%s → %d verdict(s) changed",
            self._client_name,
            keyword,
            channel,
            sum(1 for rows in written if rows),
        )
        # An answer with no file is progress: a channel finding nothing still crawls.
        return not written or any(rows is not None for rows in written)
