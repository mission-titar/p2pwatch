"""``NotificationOutboxReader``: the notifications left to send, kept in ``local.db`` so that they
survive a restart, never merged. Synchronous: a read takes a few milliseconds."""

from abc import ABC, abstractmethod

from p2pwatch.domain.observability.notification_sends import (
    PendingNotification,
    UnreadableNotification,
)


class NotificationOutboxReader(ABC):
    """Reads the notification outbox saved last."""

    @abstractmethod
    def read_pending_notifications(
        self,
    ) -> tuple[PendingNotification | UnreadableNotification, ...]:
        """The entries saved last, the oldest first, each it cannot read back unreadable, such as
        one an earlier version left; ``()`` before the first save."""
