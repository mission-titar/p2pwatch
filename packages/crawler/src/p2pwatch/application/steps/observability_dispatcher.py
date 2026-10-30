"""The dispatch step: plans an ``Event``, logs it, writes its node metrics, notifies its audience.
A notification failing or timing out is absorbed and logged: it never breaks the crawl (E-D13)."""

import asyncio
from typing import assert_never

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.node_metric_writer import NodeMetricWriter
from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.events import Event
from p2pwatch.domain.observability.node_metric import CounterIncrement
from p2pwatch.domain.observability.policy import audience_of, plan_observability
from p2pwatch.domain.observability.severity import Severity


class ObservabilityDispatcher:
    """One dispatch point, three outputs: the log line, the node metrics, the notifications."""

    def __init__(
        self,
        *,
        logger: Logger,
        node_metric_writer: NodeMetricWriter,
        notifier: Notifier,
        notification_timeout_seconds: float,
    ) -> None:
        self._logger = logger
        self._node_metric_writer = node_metric_writer
        self._notifier = notifier
        self._notification_timeout_seconds = notification_timeout_seconds

    async def dispatch(self, event: Event) -> None:
        plan = plan_observability(event)
        self._log_at_severity(plan.severity, message=plan.message)
        for instruction in plan.node_metrics:
            if isinstance(instruction, CounterIncrement):
                self._node_metric_writer.record_increment(instruction)
            else:
                self._node_metric_writer.set_gauge(instruction)
        if plan.notification is None:
            return
        audience = audience_of(plan.notification)
        try:
            await asyncio.wait_for(
                self._notifier.notify(audience, notification=plan.notification),
                timeout=self._notification_timeout_seconds,
            )
        except Exception as error:  # Notifications never break the crawl.
            self._logger.warning("notification %s failed (%s)", audience.value, error)

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
