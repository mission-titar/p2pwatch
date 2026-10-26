"""``MetricsRecorder``: fed by the dispatch step, ``ObservabilityDispatcher`` (spec Plan E §3)."""

from abc import ABC, abstractmethod

from p2pwatch.domain.observability.node_metric import CounterIncrement, GaugeSetting


class MetricsRecorder(ABC):
    """Records the metrics an event's observability plan names."""

    @abstractmethod
    def apply(self, instruction: CounterIncrement | GaugeSetting) -> None:
        """Applies one counter increment or gauge setting."""
