from collections.abc import Sequence

from p2pwatch.application.ports.driven.notification_outbox_reader import NotificationOutboxReader
from p2pwatch.application.ports.driven.notification_outbox_writer import NotificationOutboxWriter
from p2pwatch.domain.observability.notification_sends import PendingNotification
from p2pwatch.domain.store_error import StoreError


class FakeNotificationOutboxStore(NotificationOutboxReader, NotificationOutboxWriter):
    """Keeps the entries saved last; its saves raise once told to fail."""

    def __init__(self) -> None:
        self.writes_fail = False
        self._entries: tuple[PendingNotification, ...] = ()

    def read_pending_notifications(self) -> tuple[PendingNotification, ...]:
        return self._entries

    def set_pending_notifications(self, entries: Sequence[PendingNotification]) -> None:
        if self.writes_fail:
            raise StoreError("disk I/O error")
        self._entries = tuple(entries)
