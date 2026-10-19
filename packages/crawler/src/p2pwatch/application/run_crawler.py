"""``RunCrawler``: the root of the crawler's graph, which the composition invokes once built."""

import asyncio
from collections.abc import Awaitable, Callable, Coroutine, Sequence

from p2pwatch.application.reevaluate_catalog import ReevaluationSummary
from p2pwatch.application.reevaluate_if_policy_changed import reevaluate_if_policy_changed
from p2pwatch.application.resolve_node_id import resolve_node_id
from p2pwatch.application.supervise_loops import supervise_loops
from p2pwatch.domain.observability.events import CrawlerStarted
from p2pwatch.ports.driven.clock import WallClock
from p2pwatch.ports.driven.local_state_repository import LocalStateRepository
from p2pwatch.ports.driven.logger import Logger
from p2pwatch.ports.driven.node_id import NodeIdGenerator, NodeIdReader, NodeIdWriter
from p2pwatch.ports.driven.telemetry import Telemetry


class RunCrawler:
    """Resolves the node's id, announces the start, re-evaluates, then runs the loops."""

    def __init__(
        self,
        *,
        configured_node_id: str | None,
        node_id_reader: NodeIdReader,
        node_id_writer: NodeIdWriter,
        node_id_generator: NodeIdGenerator,
        wall_clock: WallClock,
        telemetry: Telemetry,
        policy_fingerprint: str,
        local_state: LocalStateRepository,
        reevaluate: Callable[[str], Awaitable[ReevaluationSummary]],
        loops: Sequence[Callable[[str], Coroutine[object, object, None]]],
        download_enabled: bool,
        shutdown: asyncio.Event,
        logger: Logger,
        reevaluation_gate_logger: Logger,
    ) -> None:
        self._configured_node_id = configured_node_id
        self._node_id_reader = node_id_reader
        self._node_id_writer = node_id_writer
        self._node_id_generator = node_id_generator
        self._wall_clock = wall_clock
        self._telemetry = telemetry
        self._policy_fingerprint = policy_fingerprint
        self._local_state = local_state
        self._reevaluate = reevaluate
        self._loops = loops
        self._download_enabled = download_enabled
        self._shutdown = shutdown
        self._logger = logger
        self._reevaluation_gate_logger = reevaluation_gate_logger

    async def run(self, *, arm_shutdown_bound: Callable[[], None]) -> None:
        """Runs until ``shutdown``, calling ``arm_shutdown_bound`` before the loops unwind."""
        node_id = resolve_node_id(
            self._configured_node_id,
            node_id_reader=self._node_id_reader,
            node_id_writer=self._node_id_writer,
            node_id_generator=self._node_id_generator,
            wall_clock=self._wall_clock,
        )
        self._logger.info("crawler started: node_id=%s", node_id)
        if self._download_enabled:
            self._logger.info("download enabled: download loop armed")
        await self._telemetry.emit(CrawlerStarted(download_enabled=self._download_enabled), node_id)
        # Before the loops, so the first search's tier actions (download wake, notify) see the
        # current policy. A comment-only edit of matcher.yml or targets.yml still runs one pass.
        await reevaluate_if_policy_changed(
            fingerprint=self._policy_fingerprint,
            local_repo=self._local_state,
            reevaluate=lambda: self._reevaluate(node_id),
            logger=self._reevaluation_gate_logger,
        )
        await supervise_loops(
            [_with_node_id(loop, node_id) for loop in self._loops],
            shutdown=self._shutdown,
            arm_shutdown_bound=arm_shutdown_bound,
        )


def _with_node_id(
    loop: Callable[[str], Coroutine[object, object, None]], node_id: str
) -> Callable[[], Coroutine[object, object, None]]:
    return lambda: loop(node_id)
