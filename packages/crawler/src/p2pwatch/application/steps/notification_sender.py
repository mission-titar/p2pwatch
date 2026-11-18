"""The notifier's work: sends each notification left in the outbox, the oldest first, such as a
tier rise to the community's Discord webhook, and records on its service whether the send failed."""

import asyncio
from collections.abc import Mapping
from typing import Literal, Protocol

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.application.steps.notification_outbox import NotificationOutbox
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.health.external_dependency import ExternalDependency
from p2pwatch.domain.health.health_rule import HealthRule
from p2pwatch.domain.observability.notification_sends import (
    SENDS_FAILED,
    NotificationRefusedError,
    NotificationService,
    PendingNotification,
)


# Records one check of a rule on a part, such as ``NodeHealth.record``.
class CheckRecorder(Protocol):
    async def __call__(
        self, *, on: ExternalDependency, rule: HealthRule, detected: bool
    ) -> None: ...


# How a send that met no bug ended: failed is refused by its service, or past the timeout.
type _SendEnd = Literal["sent", "failed"]


class NotificationSender(Work):
    """Sends the oldest notification left at each turn, a turn waiting until the outbox holds one;
    a send cancelled, by a rebuild or the shutdown, keeps its entry for the next."""

    def __init__(
        self,
        *,
        outbox: NotificationOutbox,
        notifier: Notifier,
        notification_timeout_seconds: float,
        record_check: CheckRecorder,
        service_dependencies: Mapping[NotificationService, ExternalDependency],
        logger: Logger,
    ) -> None:
        self._outbox = outbox
        self._notifier = notifier
        self._notification_timeout_seconds = notification_timeout_seconds
        self._record_check = record_check
        self._service_dependencies = service_dependencies
        self._logger = logger

    def __str__(self) -> str:
        return "notification sending"

    async def wait_for_next_turn(self) -> None:
        """Returns once the outbox holds a notification."""
        await self._outbox.wait_for_an_entry()

    async def run_once(self) -> None:
        """Sends the oldest notification left within the notification timeout, then removes it, a
        refusal or a timeout recorded on its service's sends, a bug raised."""
        entry = self._outbox.oldest()
        if entry is None:
            return
        end = await self._end_of_send(entry)  # a cancellation keeps the entry for the next turn
        self._outbox.remove(entry)
        if isinstance(end, Exception):
            raise end
        part = self._service_dependencies[entry.service]
        await self._record_check(on=part, rule=SENDS_FAILED, detected=end == "failed")

    async def send_what_is_left(self) -> None:
        """Sends every notification left, the oldest first, as its turns do, a bug logged with its
        trace: at the shutdown, once every work has stopped."""
        while self._outbox.oldest() is not None:
            try:
                await self.run_once()
            except Exception as error:  # the boundary of a turn, the supervisor gone by now
                self._logger.exception("bug in %s", self, error=error)

    async def _end_of_send(self, entry: PendingNotification) -> _SendEnd | Exception:
        """How the send of ``entry`` ended, a failed one logged in one line, a bug returned."""
        part_name = self._service_dependencies[entry.service].name
        try:
            raised = await asyncio.wait_for(
                self._raised_by(entry), timeout=self._notification_timeout_seconds
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
        return raised

    async def _raised_by(self, entry: PendingNotification) -> Exception | None:
        """What the notifier raised, if anything: returned, so that a ``TimeoutError`` of its own
        is never read as the send past its timeout."""
        try:
            await self._notifier.notify(entry.service, notification=entry.notification)
        except Exception as error:  # the boundary of a send, by design
            return error
        return None
