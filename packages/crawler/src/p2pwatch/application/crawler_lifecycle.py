"""``CrawlerLifecycle``: the root of the crawler's graph, which the composition runs once built."""

import asyncio
from collections.abc import Awaitable, Callable, Coroutine, Sequence

from p2pwatch.application.ports.driven.backoff_state_reader import BackoffStateReader
from p2pwatch.application.ports.driven.event_emitter import EventEmitter
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.node_id_generator import NodeIdGenerator
from p2pwatch.application.ports.driven.node_id_reader import NodeIdReader
from p2pwatch.application.ports.driven.node_id_writer import NodeIdWriter
from p2pwatch.application.ports.driven.policy_fingerprint_reader import PolicyFingerprintReader
from p2pwatch.application.ports.driven.policy_fingerprint_writer import PolicyFingerprintWriter
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.reevaluate_catalog import ReevaluationSummary
from p2pwatch.application.steps.reevaluate_if_policy_changed import reevaluate_if_policy_changed
from p2pwatch.application.steps.resolve_node_id import resolve_node_id
from p2pwatch.application.steps.resume_backoff_waits import resume_backoff_waits
from p2pwatch.application.steps.search_worker import BackoffRegistry
from p2pwatch.application.steps.supervise_loops import supervise_loops
from p2pwatch.domain.observability.events import CrawlerStarted


class CrawlerLifecycle:
    """Resolves the node's id, resumes the backoff, announces the start, re-evaluates, then runs
    the loops."""

    def __init__(
        self,
        *,
        configured_node_id: str | None,
        node_id_reader: NodeIdReader,
        node_id_writer: NodeIdWriter,
        node_id_generator: NodeIdGenerator,
        wall_clock: WallClock,
        event_emitter: EventEmitter,
        policy_fingerprint: str,
        policy_fingerprint_reader: PolicyFingerprintReader,
        policy_fingerprint_writer: PolicyFingerprintWriter,
        reevaluate: Callable[[str], Awaitable[ReevaluationSummary]],
        backoff: BackoffRegistry,
        backoff_state_reader: BackoffStateReader,
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
        self._event_emitter = event_emitter
        self._policy_fingerprint = policy_fingerprint
        self._policy_fingerprint_reader = policy_fingerprint_reader
        self._policy_fingerprint_writer = policy_fingerprint_writer
        self._reevaluate = reevaluate
        self._backoff = backoff
        self._backoff_state_reader = backoff_state_reader
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
        resume_backoff_waits(self._backoff, self._backoff_state_reader)
        self._logger.info("crawler started: node_id=%s", node_id)
        if self._download_enabled:
            self._logger.info("download enabled: download loop armed")
        await self._event_emitter.emit(
            CrawlerStarted(download_enabled=self._download_enabled), node_id
        )
        # Before the loops, so the first search's tier actions (download wake, notify) see the
        # current policy. A comment-only edit of matcher.yml or targets.yml still runs one pass.
        await reevaluate_if_policy_changed(
            fingerprint=self._policy_fingerprint,
            policy_fingerprint_reader=self._policy_fingerprint_reader,
            policy_fingerprint_writer=self._policy_fingerprint_writer,
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
