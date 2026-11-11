"""``CrawlerLifecycle``: the root of the crawler's graph, which the composition runs once built."""

from collections.abc import Sequence

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.steps.backoff_registry import BackoffRegistry
from p2pwatch.application.steps.catalog_reevaluator import CatalogReevaluator
from p2pwatch.application.steps.loop_supervisor import (
    LoopSupervisor,
    ShutdownBoundArmer,
    SupervisedLoop,
)
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.events import CrawlerStarted


class CrawlerLifecycle:
    """Resumes the backoff, announces the start under the node's id, re-evaluates, then runs
    the loops."""

    def __init__(
        self,
        *,
        node_id: NodeId,
        observability_dispatcher: ObservabilityDispatcher,
        catalog_reevaluator: CatalogReevaluator,
        backoff: BackoffRegistry,
        loops: Sequence[SupervisedLoop],
        download_enabled: bool,
        loop_supervisor: LoopSupervisor,
        logger: Logger,
    ) -> None:
        self._node_id = node_id
        self._observability_dispatcher = observability_dispatcher
        self._catalog_reevaluator = catalog_reevaluator
        self._backoff = backoff
        self._loops = loops
        self._download_enabled = download_enabled
        self._loop_supervisor = loop_supervisor
        self._logger = logger

    async def run(self, *, arm_shutdown_bound: ShutdownBoundArmer) -> None:
        """Runs until the shutdown is requested, arming the bound before the loops unwind."""
        self._backoff.resume_waits()
        self._logger.info("crawler started: node_id=%s", self._node_id)
        if self._download_enabled:
            self._logger.info("download enabled: download loop armed")
        await self._observability_dispatcher.dispatch(
            CrawlerStarted(download_enabled=self._download_enabled, node_id=self._node_id)
        )
        # Before the loops, so the first search's tier actions (download wake, notify) see the
        # current policy. A comment-only edit of matcher.yml or targets.yml still runs one pass.
        await self._catalog_reevaluator.reevaluate_if_policy_changed()
        await self._loop_supervisor.supervise(self._loops, arm_shutdown_bound=arm_shutdown_bound)
