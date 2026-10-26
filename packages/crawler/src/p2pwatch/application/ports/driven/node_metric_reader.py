"""``NodeMetricReader``: reads the node metrics' samples."""

from abc import ABC, abstractmethod

from p2pwatch.domain.observability.node_metric import NodeMetricSample


class NodeMetricReader(ABC):
    """Reads the node metrics, from any thread."""

    @abstractmethod
    def read_samples(self) -> tuple[NodeMetricSample, ...]:
        """Every series written and not removed, each with its current value."""
