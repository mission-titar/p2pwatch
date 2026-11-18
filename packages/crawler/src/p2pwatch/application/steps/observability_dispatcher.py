"""The dispatch step: plans an ``Event``, logs it, writes its node metrics, and leaves its
notification for each service of its audience, awaiting nothing, for the notifier's work to send."""

import asyncio
from collections.abc import Awaitable, Sequence
from contextlib import suppress
from typing import Protocol, assert_never

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.node_metric_writer import NodeMetricWriter
from p2pwatch.domain.observability.events import Event
from p2pwatch.domain.observability.node_metric import CounterIncrement
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notification_sends import NotificationService
from p2pwatch.domain.observability.policy import audience_of, plan_observability
from p2pwatch.domain.observability.severity import Severity


# Leaves ``notification`` to send to each of ``services``, such as ``NotificationOutbox.leave``.
class NotificationLeaver(Protocol):
    def __call__(
        self, notification: Notification, *, services: Sequence[NotificationService]
    ) -> None: ...


class ObservabilityDispatcher:
    """One dispatch point, three outputs: the log line, the node metrics, and the notification,
    such as a tier rise left for the community's Discord webhook."""

    def __init__(
        self,
        *,
        logger: Logger,
        node_metric_writer: NodeMetricWriter,
        leave_notification: NotificationLeaver,
        services: Sequence[NotificationService],
    ) -> None:
        self._logger = logger
        self._node_metric_writer = node_metric_writer
        self._leave_notification = leave_notification
        self._services = services
        # Held to their end: the loop keeps only a weak reference to a task (see asyncio.shield).
        self._shielded_dispatches: set[Awaitable[None]] = set()

    async def dispatch(self, event: Event) -> None:
        """Logs ``event``, writes its node metrics and leaves its notification, with no await: a
        turn cut after a decision's write has left its notification."""
        plan = plan_observability(event)
        self._log_at_severity(plan.severity, message=plan.message)
        for instruction in plan.node_metrics:
            if isinstance(instruction, CounterIncrement):
                self._node_metric_writer.record_increment(instruction)
            else:
                self._node_metric_writer.set_gauge(instruction)
        if plan.notification is not None:
            audience = audience_of(plan.notification)
            services = [service for service in self._services if service.audience is audience]
            self._leave_notification(plan.notification, services=services)

    async def dispatch_shielded(self, event: Event) -> None:
        """Dispatches ``event`` in a task of its own, which goes on when the caller is cancelled:
        a turn cut by its time limit or a rebuild right after a decision's write still leaves it."""
        dispatch = asyncio.ensure_future(self.dispatch(event))
        self._shielded_dispatches.add(dispatch)
        dispatch.add_done_callback(self._shielded_dispatches.discard)
        try:
            await asyncio.shield(dispatch)
        except asyncio.CancelledError:
            # No turn will see a bug of the dispatch from now on: logged here instead, once it ends.
            dispatch.add_done_callback(
                lambda left: (
                    None if left.cancelled() else self._log_a_bug(left.exception(), event=event)
                )
            )
            raise

    async def finish_shielded_dispatches(self) -> None:
        """Waits for the shielded dispatches not ended yet, such as a completion's whose turn the
        shutdown cut: their notifications are left before the outbox's last sends."""
        for dispatch in tuple(self._shielded_dispatches):
            with suppress(Exception):  # logged by its done callback, its caller gone
                await asyncio.shield(dispatch)

    def _log_a_bug(self, bug: BaseException | None, *, event: Event) -> None:
        """Logs ``bug``, if any, of a shielded dispatch whose caller has left."""
        if bug is not None:
            self._logger.exception("bug in the notification of %s", type(event).__name__, error=bug)

    def _log_at_severity(self, severity: Severity, *, message: str) -> None:
        """Writes ``message`` at the level ``severity`` maps to, a success being an info."""
        match severity:
            case Severity.DEBUG:
                self._logger.debug(message)
            case Severity.INFO | Severity.SUCCESS:
                self._logger.info(message)
            case Severity.WARNING:
                self._logger.warning(message)
            case _:  # pragma: no cover
                assert_never(severity)
