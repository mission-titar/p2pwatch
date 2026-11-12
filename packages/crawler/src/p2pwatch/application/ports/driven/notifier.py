"""``Notifier``: fed by the dispatch step, ``ObservabilityDispatcher`` (spec Plan E §3)."""

from abc import ABC, abstractmethod

from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notifier_outcomes import NotificationService


class Notifier(ABC):
    """Lists its services and notifies one of them at each call."""

    @abstractmethod
    def services(self) -> tuple[NotificationService, ...]:
        """Its services, each audience's in the order configured: the same from a notifier built
        anew on the same configuration."""

    @abstractmethod
    async def notify(self, service: NotificationService, *, notification: Notification) -> None:
        """Sends one notification to ``service``, one of its services, titled for the node it
        carries; raises ``NotificationRefused`` when the service refuses it or fails to deliver
        it."""
