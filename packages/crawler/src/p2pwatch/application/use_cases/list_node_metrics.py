"""Lists the node metrics from the samples the store holds."""

from p2pwatch.application.ports.driven.node_metric_reader import NodeMetricReader
from p2pwatch.application.ports.driving.node_metric_lister import (
    NodeMetricLister,
    NodeMetricListing,
)
from p2pwatch.domain.observability.node_metric import (
    NodeCounter,
    NodeGauge,
    NodeMetricSample,
)


class ListNodeMetrics(NodeMetricLister):
    def __init__(self, node_metric_reader: NodeMetricReader) -> None:
        self._node_metric_reader = node_metric_reader

    def list_node_metrics(self) -> NodeMetricListing:
        samples = self._node_metric_reader.read_samples()
        return NodeMetricListing(
            {
                node_metric: tuple(
                    sample for sample in samples if sample.node_metric is node_metric
                )
                or _unwritten_samples(node_metric)
                for node_metric in (*NodeCounter, *NodeGauge)
            }
        )


def _unwritten_samples(node_metric: NodeCounter | NodeGauge) -> tuple[NodeMetricSample, ...]:
    """An unlabelled node metric has its one series before any write; a labelled one has none."""
    return (
        ()
        if node_metric.label_names
        else (NodeMetricSample(node_metric=node_metric, labels=(), value=0.0),)
    )
