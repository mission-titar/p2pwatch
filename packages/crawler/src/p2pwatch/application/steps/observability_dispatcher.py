"""The dispatch step: plans an ``Event``, logs it, writes its node metrics, notifies its audience.
A send that fails never breaks the crawl: it is logged, and recorded on the notifier's part."""

import asyncio
from collections.abc import Awaitable
from contextlib import suppress
from typing import Protocol, assert_never

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


class ObservabilityDispatcher:
    """One dispatch point, three outputs: the log line, the node metrics, the notifications."""

    def __init__(
        self,
        *,
        logger: Logger,
        node_metric_writer: NodeMetricWriter,
        current_notifier: CurrentNotifier,
        notification_timeout_seconds: float,
        record_check: CheckRecorder,
        notifier_component: Component,
    ) -> None:
        self._logger = logger
        self._node_metric_writer = node_metric_writer
        self._current_notifier = current_notifier
        self._notification_timeout_seconds = notification_timeout_seconds
        self._record_check = record_check
        self._notifier_component = notifier_component
        # Held to their end: the loop keeps only a weak reference to a task (see asyncio.shield).
        self._shielded_dispatches: set[Awaitable[None]] = set()

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
        """Sends ``notification`` within the notification timeout, then records how the send
        ended on the notifier's part, such as a refusal on its sends that failed."""
        audience, notifier = audience_of(notification).value, self._notifier_component
        try:
            raised = await asyncio.wait_for(
                self._raised_by_notifier(notification),
                timeout=self._notification_timeout_seconds,
            )
        except TimeoutError:
            seconds = self._notification_timeout_seconds
            message = "%s: %s notification not sent: past its timeout of %g s"
            self._logger.warning(message, notifier.name, audience, seconds)
            await self._record_no_bug(failed=True)
            return
        if raised is None:
            await self._record_no_bug(failed=False)
        elif isinstance(raised, NotificationRefusedError):
            message = "%s: %s notification not sent: %s"
            self._logger.warning(message, notifier.name, audience, raised)
            await self._record_no_bug(failed=True)
        else:
            message = "bug in %s, sending a %s notification"
            self._logger.exception(message, notifier.name, audience, error=raised)
            await self._record_check(on=notifier, rule=BUGS, detected=True)

    async def _raised_by_notifier(self, notification: Notification) -> Exception | None:
        """What the notifier raised, if anything: returned, so that a ``TimeoutError`` of its own
        is never read as the send past its timeout."""
        try:
            await self._current_notifier().notify(
                audience_of(notification), notification=notification
            )
        except Exception as error:  # the boundary of a send, by design
            return error
        return None

    async def _record_no_bug(self, *, failed: bool) -> None:
        """Records a send that met no bug, and whether it failed, such as a refusal."""
        notifier = self._notifier_component
        await self._record_check(on=notifier, rule=BUGS, detected=False)
        await self._record_check(on=notifier, rule=SENDS_FAILED, detected=failed)

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
