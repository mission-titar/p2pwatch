"""``MetricsRecorder``: fed by the ``EventEmitter``'s dispatcher (spec Plan E §3)."""

from abc import ABC, abstractmethod

from p2pwatch.domain.observability.policy import MetricInstruction


class MetricsRecorder(ABC):
    """Records the metrics an event's observability plan names."""

    @abstractmethod
    def apply(self, instruction: MetricInstruction) -> None:
        """Applies one metric instruction."""
