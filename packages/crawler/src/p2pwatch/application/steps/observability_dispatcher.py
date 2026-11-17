"""The dispatch step: plans an ``Event``, logs it, writes its node metrics, notifies its audience.
A notification failing or timing out is absorbed and logged: it never breaks the crawl."""

import asyncio
from collections.abc import Awaitable
from contextlib import suppress
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
