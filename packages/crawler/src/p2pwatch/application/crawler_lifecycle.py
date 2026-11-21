"""``CrawlerLifecycle``: the root of the crawler's graph, which the composition runs once built."""

import asyncio
from collections.abc import Sequence

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.steps.backoff_registry import BackoffRegistry
from p2pwatch.application.steps.catalog_reevaluator import CatalogReevaluator
from p2pwatch.application.steps.notification_sender import NotificationSender, empty_the_outbox
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.supervisor import ShutdownBoundArmer, Supervisor
from p2pwatch.domain.crawler_restart_error import CrawlerRestartError
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.events import CrawlerFunctionLost, CrawlerStarted


class CrawlerLifecycle:
    """Resumes the saved backoffs, announces the node online, re-evaluates the catalog if the
    policy changed, has the supervisor run the works of the objects it built, then sends the
    notifications left, a function lost's alert among them."""

    def __init__(
        self,
        *,
        node_id: NodeId,
        observability_dispatcher: ObservabilityDispatcher,
        catalog_reevaluator: CatalogReevaluator,
        backoff: BackoffRegistry,
        download_enabled: bool,
        supervisor: Supervisor,
        notification_senders: Sequence[NotificationSender],
        logger: Logger,
    ) -> None:
        self._node_id = node_id
        self._observability_dispatcher = observability_dispatcher
        self._catalog_reevaluator = catalog_reevaluator
        self._backoff = backoff
        self._download_enabled = download_enabled
        self._supervisor = supervisor
        self._notification_senders = notification_senders
        self._logger = logger

    async def run(self, *, arm_shutdown_bound: ShutdownBoundArmer) -> None:
        """Runs until the shutdown is requested, then sends what the outbox holds within the bound
        it arms; a function lost raises its ``CrawlerRestartError``, its alert sent or cut."""
        self._backoff.resume_waits()
        self._logger.info("crawler started: node_id=%s", self._node_id)
        if self._download_enabled:
            self._logger.info("download enabled: download loop armed")
        await self._observability_dispatcher.dispatch(
            CrawlerStarted(download_enabled=self._download_enabled, node_id=self._node_id)
        )
        # Before the works, so the first search's tier actions (download wake, notify) see the
        # current policy. A comment-only edit of matcher.yml or targets.yml still runs one pass.
        await self._catalog_reevaluator.reevaluate_if_policy_changed()
        try:
            await self._supervisor.supervise(arm_shutdown_bound=arm_shutdown_bound)
        except CrawlerRestartError as restart:
            await self._observability_dispatcher.dispatch(
                CrawlerFunctionLost(
                    function=restart.function,
                    rebuilds=restart.rebuilds,
                    node_id=self._node_id,
                )
            )
            try:
                await empty_the_outbox(self._notification_senders)
            except asyncio.CancelledError as cut:  # by the shutdown deadline: a restart still
                raise restart from cut
            raise
        await empty_the_outbox(self._notification_senders)
