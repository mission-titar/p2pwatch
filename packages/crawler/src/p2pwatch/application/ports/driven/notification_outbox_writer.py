"""``NotificationOutboxWriter``: the notifications left to send, kept in ``local.db`` so that they
survive a restart, never merged. Synchronous: a write takes a few milliseconds."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from p2pwatch.domain.observability.notification_sends import PendingNotification


class NotificationOutboxWriter(ABC):
    """Saves the notification outbox."""

    @abstractmethod
    def set_pending_notifications(self, entries: Sequence[PendingNotification]) -> None:
        """Replaces every entry saved before with ``entries``, the oldest first."""
