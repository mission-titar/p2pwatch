"""The dispatch step: plans an ``Event``, logs it, writes its node metrics, and leaves its
notification for each service of its audience but the one its plan skips, awaiting nothing, for
the notifier's work to send."""

from collections.abc import Sequence
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
            services = [
                service
                for service in self._services
                if service.audience is audience and str(service) != plan.skipped_service
            ]
            self._leave_notification(plan.notification, services=services)

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
