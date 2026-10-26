"""``NodeMetricWriter``: writes the node metrics an event's observability plan names."""

from abc import ABC, abstractmethod

from p2pwatch.domain.observability.node_metric import CounterIncrement, GaugeSetting


class NodeMetricWriter(ABC):
    """Writes the node metrics, from the crawler's loop alone."""

    @abstractmethod
    def record_increment(self, increment: CounterIncrement) -> None:
        """Adds its amount to its series, which an amount of 0 creates at 0."""

    @abstractmethod
    def set_gauge(self, setting: GaugeSetting) -> None:
        """Replaces its series with its value, or removes it, if present, when it is ``None``."""
