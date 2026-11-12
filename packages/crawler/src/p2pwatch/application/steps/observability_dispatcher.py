"""The dispatch step: plans an ``Event``, logs it, writes its node metrics, notifies its audience.
Each notification's outcome is recorded on the notifier's component, a refusal or a send past the
timeout declared, any other exception a bug: none breaks the crawl (E-D13, spec v5 lot 4, D3)."""

import asyncio
from typing import Protocol, assert_never

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.node_metric_writer import NodeMetricWriter
from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.outcome import TURNS, Outcome, OutcomeSource
from p2pwatch.domain.observability.events import Event
from p2pwatch.domain.observability.node_metric import CounterIncrement
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notifier_outcomes import (
    NotificationRefused,
    NotificationTimedOut,
)
from p2pwatch.domain.observability.policy import audience_of, plan_observability
from p2pwatch.domain.observability.severity import Severity


# The notifier each send reaches: its owner may build it anew between two sends.
class CurrentNotifier(Protocol):
    def __call__(self) -> Notifier: ...


class OutcomeRecorder(Protocol):
    async def __call__(self, outcome: Outcome, *, on: Component, by: OutcomeSource) -> None: ...


class ObservabilityDispatcher:
    """One dispatch point, three outputs: the log line, the node metrics, the notifications."""

    def __init__(
        self,
        *,
        logger: Logger,
        node_metric_writer: NodeMetricWriter,
        current_notifier: CurrentNotifier,
        notification_timeout_seconds: float,
        record_outcome: OutcomeRecorder,
        notifier_component: Component,
    ) -> None:
        self._logger = logger
        self._node_metric_writer = node_metric_writer
        self._current_notifier = current_notifier
        self._notification_timeout_seconds = notification_timeout_seconds
        self._record_outcome = record_outcome
        self._notifier_component = notifier_component

    async def dispatch(self, event: Event) -> None:
        plan = plan_observability(event)
        self._log_at_severity(plan.severity, message=plan.message)
        for instruction in plan.node_metrics:
            if isinstance(instruction, CounterIncrement):
                self._node_metric_writer.record_increment(instruction)
            else:
                self._node_metric_writer.set_gauge(instruction)
        if plan.notification is not None:
            outcome = await self._outcome_of(plan.notification)
            await self._record_outcome(outcome, on=self._notifier_component, by=TURNS)

    async def _outcome_of(self, notification: Notification) -> Outcome:
        audience = audience_of(notification)
        try:
            await asyncio.wait_for(
                self._current_notifier().notify(audience, notification=notification),
                timeout=self._notification_timeout_seconds,
            )
        except NotificationRefused as refusal:
            self._logger.warning("notification %s: %s", audience.value, refusal)
            return Outcome.declared(refusal)
        except TimeoutError:
            timed_out = NotificationTimedOut(
                f"past its timeout of {self._notification_timeout_seconds} s"
            )
            self._logger.warning("notification %s: %s", audience.value, timed_out)
            return Outcome.declared(timed_out)
        except Exception as error:  # the send's boundary, by design: any other is a bug
            self._logger.exception("bug in notification %s", audience.value, error=error)
            return Outcome.bug(repr(error))
        return Outcome.success()

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
