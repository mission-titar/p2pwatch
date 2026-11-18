"""The notifications left to send, such as a tier rise for the community's Discord webhook: a turn
leaves one without awaiting anything, and the notifier's work sends it; saved at each change, so a
notification survives a restart."""

from collections.abc import Collection, Sequence

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.notification_outbox_reader import NotificationOutboxReader
from p2pwatch.application.ports.driven.notification_outbox_writer import NotificationOutboxWriter
from p2pwatch.application.ports.driven.waker import Waker
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notification_sends import (
    NotificationService,
    PendingNotification,
)
from p2pwatch.domain.store_error import StoreError
from p2pwatch.domain.wake_subject import WakeSubject


class NotificationOutbox:
    """The notifications left to send, in memory, one entry per notification and service, the
    oldest first; it sends from memory whether or not its saves work."""

    def __init__(
        self,
        *,
        writer: NotificationOutboxWriter,
        reader: NotificationOutboxReader,
        services: Collection[NotificationService],
        waker: Waker,
        logger: Logger,
    ) -> None:
        """Reads back the entries saved last, such as a tier rise a stop left unsent, those for a
        service of none of ``services`` dropped."""
        self._writer = writer
        self._waker = waker
        self._logger = logger
        self._latest_save_failed = False
        saved = reader.read_pending_notifications()
        self._entries = [entry for entry in saved if entry.service in services]
        if dropped := [entry.service for entry in saved if entry.service not in services]:
            gone = ", ".join(sorted({str(service) for service in dropped}))
            message = "%d notification(s) dropped, their service no longer configured: %s"
            self._logger.warning(message, len(dropped), gone)
            self._save()

    def leave(self, notification: Notification, *, services: Sequence[NotificationService]) -> None:
        """Adds an entry for each of ``services``, such as the community's Discord webhook, and
        wakes the notifier's work."""
        self._entries.extend(
            PendingNotification(notification=notification, service=service) for service in services
        )
        self._save()
        self._waker.wake(WakeSubject.NOTIFICATION)

    @property
    def latest_save_failed(self) -> bool:
        """Whether its latest save failed, such as on a full disk; ``False`` before the first."""
        return self._latest_save_failed

    def oldest(self) -> PendingNotification | None:
        """The entry left first, ``None`` when it holds none."""
        return self._entries[0] if self._entries else None

    def remove(self, entry: PendingNotification) -> None:
        """Removes ``entry`` once its send has ended."""
        self._entries.remove(entry)
        self._save()

    async def wait_for_an_entry(self) -> None:
        """Returns once it holds an entry, at once if it already does."""
        while not self._entries:  # a wake left by a notification since sent finds none
            await self._waker.wait(WakeSubject.NOTIFICATION)

    def _save(self) -> None:
        try:
            self._writer.set_pending_notifications(self._entries)
        except StoreError as error:
            self._logger.warning(
                "notification outbox not saved (%s): saved again at its next change", error
            )
            self._latest_save_failed = True
        else:
            self._latest_save_failed = False
