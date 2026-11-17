"""``Notifier``: fed by the dispatch step, ``ObservabilityDispatcher`` (spec Plan E §3)."""

from abc import ABC, abstractmethod

from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notification_sends import NotificationService


class Notifier(ABC):
    """Sends notifications to the services it lists, such as a Discord webhook for the community."""

    @abstractmethod
    def services(self) -> tuple[NotificationService, ...]:
        """Its services, in the order configured: equal from a notifier built anew on the same
        configuration, so a rebuilt notifier sends to the services the node judges."""

    @abstractmethod
    async def notify(self, service: NotificationService, *, notification: Notification) -> None:
        """Sends one notification to ``service``, under the name of the node it carries; raises
        ``NotificationRefusedError`` when the service refuses it."""
