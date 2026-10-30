"""``Notifier``: fed by the dispatch step, ``ObservabilityDispatcher`` (spec Plan E §3)."""

from abc import ABC, abstractmethod

from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.policy import Audience


class Notifier(ABC):
    """Notifies an audience of an event."""

    @abstractmethod
    async def notify(self, audience: Audience, *, notification: Notification) -> None:
        """Sends one notification, titled for the node it carries."""
