"""``NotificationOutboxReader``: the notifications left to send, kept in ``local.db`` so that they
survive a restart, never merged. Synchronous: a read takes a few milliseconds."""

from abc import ABC, abstractmethod

from p2pwatch.domain.observability.notification_sends import PendingNotification


class NotificationOutboxReader(ABC):
    """Reads the notification outbox saved last."""

    @abstractmethod
    def read_pending_notifications(self) -> tuple[PendingNotification, ...]:
        """The entries saved last, the oldest first, ``()`` before the first save."""
