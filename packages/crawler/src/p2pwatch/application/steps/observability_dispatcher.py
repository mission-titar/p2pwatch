"""The dispatch step: plans an ``Event``, logs it, writes its node metrics, notifies each service
of its audience. A send that fails never breaks the crawl: it is logged, and recorded on the
service's part."""

import asyncio
from collections.abc import Awaitable, Mapping
from contextlib import suppress
from typing import Literal, Protocol, assert_never

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.node_metric_writer import NodeMetricWriter
from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.health_rule import HealthRule
from p2pwatch.domain.observability.events import Event
from p2pwatch.domain.observability.node_metric import CounterIncrement
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notification_sends import (
    SENDS_FAILED,
    NotificationRefusedError,
    NotificationService,
)
from p2pwatch.domain.observability.policy import audience_of, plan_observability
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.work_components import BUGS


# The notifier a send goes to, such as the one the composition rebuilt latest.
class CurrentNotifier(Protocol):
    def __call__(self) -> Notifier: ...


# Records one check of a rule on a part, such as ``NodeHealth.record``.
class CheckRecorder(Protocol):
    async def __call__(self, *, on: Component, rule: HealthRule, detected: bool) -> None: ...


# How one send to one service ended: failed is refused by its service, or past the timeout.
type _SendEnd = Literal["sent", "failed", "bug"]


class ObservabilityDispatcher:
    """One dispatch point, four outputs: the log line, the node metrics, the notifications, and
    how each send ended, on its service's part."""

    def __init__(
        self,
        *,
        logger: Logger,
        node_metric_writer: NodeMetricWriter,
        current_notifier: CurrentNotifier,
        notification_timeout_seconds: float,
        record_check: CheckRecorder,
        service_components: Mapping[NotificationService, Component],
    ) -> None:
        self._logger = logger
        self._node_metric_writer = node_metric_writer
        self._current_notifier = current_notifier
        self._notification_timeout_seconds = notification_timeout_seconds
        self._record_check = record_check
        self._service_components = service_components
        # Held to their end: the loop keeps only a weak reference to a task (see asyncio.shield).
        self._shielded_dispatches: set[Awaitable[None]] = set()

    def service_components(self) -> tuple[Component, ...]:
        """The part of each notification service it records each send on, such as ``notifier
        discord community``."""
        return tuple(self._service_components.values())

    async def dispatch(self, event: Event) -> None:
        plan = plan_observability(event)
        self._log_at_severity(plan.severity, message=plan.message)
        for instruction in plan.node_metrics:
            if isinstance(instruction, CounterIncrement):
                self._node_metric_writer.record_increment(instruction)
            else:
                self._node_metric_writer.set_gauge(instruction)
        if plan.notification is not None:
            await self._send(plan.notification)

    async def _send(self, notification: Notification) -> None:
        """Sends ``notification`` to each service of its audience together, so that it takes one
        notification timeout at most, then records how each send ended on its service's part,
        unless the notifier was rebuilt meanwhile."""
        notifier, audience = self._current_notifier(), audience_of(notification)
        services = [service for service in self._service_components if service.audience is audience]
        async with asyncio.TaskGroup() as sends:
            ends = [
                sends.create_task(
                    self._send_to(service, notification=notification, notifier=notifier)
                )
                for service in services
            ]
        if self._current_notifier() is not notifier:
            return  # rebuilt meanwhile: the old notifier's sends tell nothing of the new one
        # Recorded once every send has ended: a check whose recording raises cuts no other send.
        for service, end in zip(services, ends, strict=True):
            await self._record(end.result(), on=self._service_components[service])

    async def _send_to(
        self, service: NotificationService, *, notification: Notification, notifier: Notifier
    ) -> _SendEnd:
        """Sends ``notification`` to ``service`` within the notification timeout, a failed send
        such as a refusal logged in one line, a bug with its trace."""
        part_name = self._service_components[service].name
        try:
            raised = await asyncio.wait_for(
                self._raised_by(notifier, service=service, notification=notification),
                timeout=self._notification_timeout_seconds,
            )
        except TimeoutError:
            seconds = self._notification_timeout_seconds
            message = "%s: notification not sent: past its timeout of %g s"
            self._logger.warning(message, part_name, seconds)
            return "failed"
        if raised is None:
            return "sent"
        if isinstance(raised, NotificationRefusedError):
            self._logger.warning("%s: notification not sent: %s", part_name, raised)
            return "failed"
        self._logger.exception("bug in %s, sending a notification", part_name, error=raised)
        return "bug"

    @staticmethod
    async def _raised_by(
        notifier: Notifier, *, service: NotificationService, notification: Notification
    ) -> Exception | None:
        """What the notifier raised, if anything: returned, so that a ``TimeoutError`` of its own
        is never read as the send past its timeout."""
        try:
            await notifier.notify(service, notification=notification)
        except Exception as error:  # the boundary of a send, by design
            return error
        return None

    async def _record(self, end: _SendEnd, *, on: Component) -> None:
        """Records how one send ended on its service's part; a bug tells nothing of whether the
        service takes the sends, so it records nothing on the sends that failed."""
        await self._record_check(on=on, rule=BUGS, detected=end == "bug")
        if end != "bug":
            await self._record_check(on=on, rule=SENDS_FAILED, detected=end == "failed")

    async def dispatch_shielded(self, event: Event) -> None:
        """Dispatches ``event`` in a task of its own, which goes on when the caller is cancelled:
        a turn cut by its time limit or a rebuild right after a decision's write still sends it."""
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
        """Waits for the shielded dispatches still sending, each within its notification timeout,
        such as a completion's whose turn the shutdown cut: they end before the resources close."""
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
