"""Observability ports (spec Plan E §3): the application emits through ``EventEmitter``, whose
dispatcher feeds a ``MetricsRecorder`` and a ``Notifier``."""

from abc import ABC, abstractmethod

from p2pwatch.domain.observability.events import Event
from p2pwatch.domain.observability.policy import Audience, MetricInstruction, Severity


class MetricsRecorder(ABC):
    """Records the metrics an event's report names."""

    @abstractmethod
    def apply(self, instruction: MetricInstruction) -> None:
        """Applies one metric instruction."""


class Notifier(ABC):
    """Notifies an audience of an event."""

    @abstractmethod
    async def notify(
        self, audience: Audience, title: str, body: str, severity: Severity, node_id: str
    ) -> None:
        """Sends one notification, titled for the node that emitted it."""


class EventEmitter(ABC):
    """Emits the application's events to metrics, logs and notifications."""

    @abstractmethod
    async def emit(self, event: Event, node_id: str) -> None:
        """Emits one event, on behalf of ``node_id``."""
