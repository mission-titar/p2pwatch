"""Observability dispatcher: routes an ``Event`` to log + metrics + notifications (E-D3/E-D13).

ADAPTER layer. Implements ``EventEmitter``. ``emit``: ``describe`` (pure) → log at the mapped
level + ``MetricsRecorder.apply`` for each metric + ``Notifier.notify`` per audience (the report's
``notification_title`` and ``notification_body``, else its message), each notification under
``asyncio.wait_for(notification_timeout_seconds)`` with failure/timeout ABSORBED + logged (a
broken notification target NEVER breaks the crawl, E-D13). No state (the edge-trigger lives in
the application, E-D8)."""

import asyncio
import logging

from p2pwatch.domain.observability.events import Event
from p2pwatch.domain.observability.policy import Severity, describe
from p2pwatch.ports.driven.telemetry import EventEmitter, MetricsRecorder, Notifier

_logger = logging.getLogger("p2pwatch.observability")

_LEVELS: dict[Severity, int] = {
    Severity.DEBUG: logging.DEBUG,
    Severity.INFO: logging.INFO,
    Severity.SUCCESS: logging.INFO,
    Severity.WARNING: logging.WARNING,
    Severity.ERROR: logging.ERROR,
}


class ObservabilityDispatcher(EventEmitter):
    """``EventEmitter`` adapter: one emission point, three outputs (log/metric/notification)."""

    def __init__(
        self,
        *,
        metrics_recorder: MetricsRecorder,
        notifier: Notifier,
        notification_timeout_seconds: float,
    ) -> None:
        self._metrics_recorder = metrics_recorder
        self._notifier = notifier
        self._notification_timeout_seconds = notification_timeout_seconds

    async def emit(self, event: Event, node_id: str) -> None:
        report = describe(event)
        _logger.log(_LEVELS[report.severity], report.message)
        for instruction in report.metrics:
            self._metrics_recorder.apply(instruction)
        for audience in report.audiences:
            try:
                await asyncio.wait_for(
                    self._notifier.notify(
                        audience,
                        report.notification_title,
                        report.notification_body or report.message,
                        report.severity,
                        node_id,
                    ),
                    timeout=self._notification_timeout_seconds,
                )
            except Exception as error:  # noqa: BLE001 (notifications NEVER break the crawl, E-D13)
                _logger.warning("notification %s failed (%s)", audience.value, error)
