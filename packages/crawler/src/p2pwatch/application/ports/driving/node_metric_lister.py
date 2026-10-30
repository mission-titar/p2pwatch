"""``NodeMetricLister``: lists the node metrics, for Prometheus."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass

from p2pwatch.domain.observability.node_metric import NodeCounter, NodeGauge, NodeMetricSample


@dataclass(kw_only=True, frozen=True)
class NodeMetricListing:
    samples_by_node_metric: Mapping[NodeCounter | NodeGauge, tuple[NodeMetricSample, ...]]


class NodeMetricLister(ABC):
    """Lists the node metrics, from any thread."""

    @abstractmethod
    def list_node_metrics(self) -> NodeMetricListing:
        """Every node counter, then every node gauge, in the catalog's order, with its samples:
        an unlabelled one never written has one at 0."""
