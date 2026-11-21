"""The notifier's work, one per service: sends each notification left for it in the outbox, the
oldest first, such as a tier rise to the community's Discord webhook, and records how it went."""

import asyncio
from collections.abc import Mapping, Sequence
from typing import Literal, Protocol

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.application.steps.notification_outbox import NotificationOutbox
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.health.external_dependency import ExternalDependency
from p2pwatch.domain.health.health_rule import HealthRule
from p2pwatch.domain.observability.notification_sends import (
    SAVES_FAILED,
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
    """Sends the oldest notification left for its service at each turn, such as the community's
    Discord webhook, a turn waiting until the outbox holds one; a cancelled send keeps its entry."""

    def __init__(
        self,
        *,
        service: NotificationService,
        outbox: NotificationOutbox,
        notifier: Notifier,
        notification_timeout_seconds: float,
        record_check: CheckRecorder,
        service_dependencies: Mapping[NotificationService, ExternalDependency],
        local_database: ExternalDependency,
        logger: Logger,
    ) -> None:
        self._service = service
        self._outbox = outbox
        self._notifier = notifier
        self._notification_timeout_seconds = notification_timeout_seconds
        self._record_check = record_check
        self._service_dependency = service_dependencies[service]
        self._local_database = local_database
        self._logger = logger

    def __str__(self) -> str:
        return f"notification sending {self._service}"

    async def wait_for_next_turn(self) -> None:
        """Returns once the outbox holds a notification for its service."""
        await self._outbox.wait_for_an_entry(self._service)

    async def run_once(self) -> None:
        """Sends its service's oldest notification within the notification timeout, then removes
        it: a failed save recorded on the local database, a refusal on its service, a bug raised."""
        entry = self._outbox.oldest(self._service)
        if entry is None:
            return
        end = await self._end_of_send(entry)  # a cancellation keeps the entry for the next turn
        self._outbox.remove(entry)
        saves_failed = self._outbox.latest_save_failed
        await self._record_check(on=self._local_database, rule=SAVES_FAILED, detected=saves_failed)
        if isinstance(end, Exception):
            raise end
        detected = end == "failed"
        await self._record_check(on=self._service_dependency, rule=SENDS_FAILED, detected=detected)

    async def send_what_is_left(self) -> bool:
        """Sends every notification left for its service, the oldest first, as its turns do, a bug
        logged with its trace; whether it took a turn, which may have left another."""
        took_a_turn = self._outbox.oldest(self._service) is not None
        while self._outbox.oldest(self._service) is not None:
            try:
                await self.run_once()
            except Exception as error:  # the boundary of a turn, the supervisor gone by now
                self._logger.exception("bug in %s", self, error=error)
        return took_a_turn

    async def _end_of_send(self, entry: PendingNotification) -> _SendEnd | Exception:
        """How the send of ``entry`` ended, a failed one logged in one line, a bug returned."""
        part_name = self._service_dependency.name
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


async def empty_the_outbox(senders: Sequence[NotificationSender]) -> None:
    """Has each of ``senders`` send what is left for its service, all at once, again while a send
    left another, such as the local database's alert: at the shutdown, once every work stopped."""
    took_a_turn = True
    while took_a_turn:
        async with asyncio.TaskGroup() as each_service:
            sending = [each_service.create_task(s.send_what_is_left()) for s in senders]
        took_a_turn = any(task.result() for task in sending)
