from p2pwatch.application.ports.driving.node_metric_lister import (
    NodeMetricLister,
    NodeMetricListing,
)


class FakeNodeMetricLister(NodeMetricLister):
    """Lists the node metrics it is given."""

    def __init__(self, node_metric_listing: NodeMetricListing) -> None:
        self._node_metric_listing = node_metric_listing

    def list_node_metrics(self) -> NodeMetricListing:
        return self._node_metric_listing
