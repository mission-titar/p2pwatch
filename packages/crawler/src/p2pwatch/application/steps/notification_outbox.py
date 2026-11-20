"""The notifications left to send, such as a tier rise for the community's Discord webhook: a turn
leaves one without awaiting anything, and the notifier's work sends it."""

from collections.abc import Sequence

from p2pwatch.application.ports.driven.waker import Waker
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notification_sends import (
    NotificationService,
    PendingNotification,
)
from p2pwatch.domain.wake_subject import WakeSubject


class NotificationOutbox:
    """The notifications left to send, in memory, one entry per notification and service, the
    oldest first."""

    def __init__(self, *, waker: Waker) -> None:
        self._waker = waker
        self._entries: list[PendingNotification] = []

    def leave(self, notification: Notification, *, services: Sequence[NotificationService]) -> None:
        """Adds an entry for each of ``services``, such as the community's Discord webhook, and
        wakes the notifier's work."""
        self._entries.extend(
            PendingNotification(notification=notification, service=service) for service in services
        )
        self._waker.wake(WakeSubject.NOTIFICATION)

    def oldest(self) -> PendingNotification | None:
        """The entry left first, ``None`` when it holds none."""
        return self._entries[0] if self._entries else None

    def remove(self, entry: PendingNotification) -> None:
        """Removes ``entry`` once its send has ended."""
        self._entries.remove(entry)

    async def wait_for_an_entry(self) -> None:
        """Returns once it holds an entry, at once if it already does."""
        while not self._entries:  # a wake left by a notification since sent finds none
            await self._waker.wait(WakeSubject.NOTIFICATION)
