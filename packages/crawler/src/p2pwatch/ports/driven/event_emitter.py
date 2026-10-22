"""``EventEmitter``: the application emits its events through it (spec Plan E §3)."""

from abc import ABC, abstractmethod

from p2pwatch.domain.observability.events import Event


class EventEmitter(ABC):
    """Emits the application's events to metrics, logs and notifications."""

    @abstractmethod
    async def emit(self, event: Event, node_id: str) -> None:
        """Emits one event, on behalf of ``node_id``."""
