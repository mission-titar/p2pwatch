"""``StallWatch``: looks every minute whether each of one client's watched functions made progress
in the latest 15 minutes, such as the crawl on amuled's kad."""

from collections.abc import Sequence

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.steps.function_progress import FunctionProgress
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.health.external_dependency import HealthAlert
from p2pwatch.domain.identifiers import ClientName, NodeId
from p2pwatch.domain.observability.events import FunctionMovingAgain, FunctionStalled
from p2pwatch.domain.status_reading import STATUS_PERIOD
from p2pwatch.domain.watched_function import STALL_AFTER, WatchedFunction


class StallWatch(Work):
    """Looks every minute at each of one client's watched functions: one without progress for
    ``STALL_AFTER`` has its stall alert opened through the node's health, ended once it moves."""

    def __init__(
        self,
        *,
        client_name: ClientName,
        watched: Sequence[WatchedFunction],
        function_progress: FunctionProgress,
        node_health: NodeHealth,
        monotonic_clock: MonotonicClock,
        node_id: NodeId,
    ) -> None:
        self._client_name = client_name
        self._watched = tuple(watched)
        self._function_progress = function_progress
        self._node_health = node_health
        self._monotonic_clock = monotonic_clock
        self._node_id = node_id
        self._looked = False

    def __str__(self) -> str:
        return f"stall watch {self._client_name}"

    async def wait_for_next_turn(self) -> None:
        """Waits a minute between two looks; the first waits nothing, so the count starts with
        the supervision."""
        if self._looked:
            await self._monotonic_clock.sleep(STATUS_PERIOD)

    async def run_once(self) -> None:
        """Opens the stall alert of each watched function without progress for ``STALL_AFTER``,
        ends that of each other."""
        self._looked = True
        for function in self._watched:
            alert = self._stall_alert(function)
            if self._function_progress.time_without_progress(function) >= STALL_AFTER:
                await self._node_health.open_alert(alert)
            else:
                await self._node_health.end_alert(about=alert.about)

    def _stall_alert(self, function: WatchedFunction) -> HealthAlert:
        return HealthAlert(
            about=f"the crawl on {function.client_name} {function.channel}, stall",
            when_failing=FunctionStalled(
                function=function,
                stalled_for_seconds=STALL_AFTER.total_seconds(),
                node_id=self._node_id,
            ),
            when_healthy_again=FunctionMovingAgain(function=function, node_id=self._node_id),
        )
