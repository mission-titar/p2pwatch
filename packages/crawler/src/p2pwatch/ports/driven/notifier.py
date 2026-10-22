"""``Notifier``: fed by the ``EventEmitter``'s dispatcher (spec Plan E §3)."""

from abc import ABC, abstractmethod

from p2pwatch.domain.observability.policy import Audience, Severity


class Notifier(ABC):
    """Notifies an audience of an event."""

    @abstractmethod
    async def notify(
        self, audience: Audience, title: str, body: str, severity: Severity, node_id: str
    ) -> None:
        """Sends one notification, titled for the node that emitted it."""
