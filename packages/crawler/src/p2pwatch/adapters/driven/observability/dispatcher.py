"""Observability dispatcher: routes an ``Event`` to log + metrics + notifications (E-D3/E-D13).

ADAPTER ring. Implements ``EventEmitter``. ``emit``: ``plan_observability`` (pure) → log at the
mapped level + ``MetricsRecorder.apply`` for each metric + ``Notifier.notify`` per audience (the
plan's ``notification_title`` and ``notification_body``, else its message), each notification under
``asyncio.wait_for(notification_timeout_seconds)`` with failure/timeout ABSORBED + logged (a
broken notification target NEVER breaks the crawl, E-D13). No state (the edge-trigger lives in
the application, E-D8)."""

import asyncio
import logging

from p2pwatch.application.ports.driven.event_emitter import EventEmitter
from p2pwatch.application.ports.driven.metrics_recorder import MetricsRecorder
from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.events import Event
from p2pwatch.domain.observability.policy import Severity, plan_observability

_logger = logging.getLogger(__name__)

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
        plan = plan_observability(event)
        _logger.log(_LEVELS[plan.severity], plan.message)
        for instruction in plan.metrics:
            self._metrics_recorder.apply(instruction)
        for audience in plan.audiences:
            try:
                await asyncio.wait_for(
                    self._notifier.notify(
                        audience,
                        plan.notification_title,
                        plan.notification_body or plan.message,
                        plan.severity,
                        node_id,
                    ),
                    timeout=self._notification_timeout_seconds,
                )
            except Exception as error:  # noqa: BLE001 (notifications NEVER break the crawl, E-D13)
                _logger.warning("notification %s failed (%s)", audience.value, error)
