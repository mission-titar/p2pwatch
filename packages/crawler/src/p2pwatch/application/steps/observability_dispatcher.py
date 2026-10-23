"""The dispatch step: plans an ``Event``, logs it, applies its metrics and notifies its audiences.
A notification failing or timing out is absorbed and logged: it never breaks the crawl (E-D13)."""

import asyncio
from typing import assert_never

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.metrics_recorder import MetricsRecorder
from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.events import Event
from p2pwatch.domain.observability.policy import plan_observability
from p2pwatch.domain.observability.severity import Severity


def log_at_severity(logger: Logger, severity: Severity, message: str) -> None:
    """Writes ``message`` at the level ``severity`` maps to, a success being an info."""
    match severity:
        case Severity.DEBUG:
            logger.debug(message)
        case Severity.INFO | Severity.SUCCESS:
            logger.info(message)
        case Severity.WARNING:
            logger.warning(message)
        case Severity.ERROR:
            logger.error(message)
        case _:  # pragma: no cover
            assert_never(severity)


class ObservabilityDispatcher:
    """One dispatch point, three outputs: the log line, the metrics, the notifications."""

    def __init__(
        self,
        *,
        logger: Logger,
        metrics_recorder: MetricsRecorder,
        notifier: Notifier,
        notification_timeout_seconds: float,
    ) -> None:
        self._logger = logger
        self._metrics_recorder = metrics_recorder
        self._notifier = notifier
        self._notification_timeout_seconds = notification_timeout_seconds

    async def dispatch(self, event: Event) -> None:
        plan = plan_observability(event)
        log_at_severity(self._logger, plan.severity, plan.message)
        for instruction in plan.metrics:
            self._metrics_recorder.apply(instruction)
        if plan.notification is None:
            return
        for audience in plan.audiences:
            try:
                await asyncio.wait_for(
                    self._notifier.notify(audience, plan.notification),
                    timeout=self._notification_timeout_seconds,
                )
            except Exception as error:  # noqa: BLE001 (notifications NEVER break the crawl, E-D13)
                self._logger.warning("notification %s failed (%s)", audience.value, error)
