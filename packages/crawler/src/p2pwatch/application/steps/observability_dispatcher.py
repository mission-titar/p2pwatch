"""The dispatch step: plans an ``Event``, logs it, writes its node metrics, notifies each service of
its audience, all together. Each send's outcome is recorded on its service's component, a refusal
or a send past the timeout declared, any other exception a bug: none breaks the crawl (E-D13,
spec v5 lot 4, D3)."""

import asyncio
from collections.abc import Mapping
from typing import Protocol, assert_never

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.node_metric_writer import NodeMetricWriter
from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.outcome import UNITS_OF_WORK, Bug, Outcome, OutcomeSource
from p2pwatch.domain.observability.events import Event
from p2pwatch.domain.observability.node_metric import CounterIncrement
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notifier_outcomes import (
    SENDS,
    NotificationRefused,
    NotificationService,
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
        service_components: Mapping[NotificationService, Component],
    ) -> None:
        self._logger = logger
        self._node_metric_writer = node_metric_writer
        self._current_notifier = current_notifier
        self._notification_timeout_seconds = notification_timeout_seconds
        self._record_outcome = record_outcome
        self._service_components = service_components

    async def dispatch(self, event: Event) -> None:
        plan = plan_observability(event)
        self._log_at_severity(plan.severity, message=plan.message)
        for instruction in plan.node_metrics:
            if isinstance(instruction, CounterIncrement):
                self._node_metric_writer.record_increment(instruction)
            else:
                self._node_metric_writer.set_gauge(instruction)
        if plan.notification is not None:
            await self._notify(plan.notification)

    async def _notify(self, notification: Notification) -> None:
        """Sends to each service of its audience together, so a notification takes one timeout
        at most, then records each send's outcome."""
        audience = audience_of(notification)
        services = [s for s in self._service_components if s.audience is audience]
        async with asyncio.TaskGroup() as group:
            sends = [
                group.create_task(self._outcome_of(s, notification=notification)) for s in services
            ]
        for service, send in zip(services, sends, strict=True):
            component, outcome = self._service_components[service], send.result()
            await self._record_outcome(outcome, on=component, by=UNITS_OF_WORK)
            if not isinstance(outcome.reason, Bug):
                await self._record_outcome(outcome, on=component, by=SENDS)

    async def _outcome_of(
        self, service: NotificationService, *, notification: Notification
    ) -> Outcome:
        named = self._service_components[service].name
        try:
            await asyncio.wait_for(
                self._current_notifier().notify(service, notification=notification),
                timeout=self._notification_timeout_seconds,
            )
        except NotificationRefused as refusal:
            self._logger.warning("%s: %s", named, refusal)
            return Outcome.declared(refusal)
        except TimeoutError:
            timed_out = NotificationTimedOut(
                f"past its timeout of {self._notification_timeout_seconds:g} s"
            )
            self._logger.warning("%s: %s", named, timed_out)
            return Outcome.declared(timed_out)
        except Exception as error:  # the send's boundary, by design: any other is a bug
            self._logger.exception("bug in %s", named, error=error)
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
