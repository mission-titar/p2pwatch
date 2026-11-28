"""Describes the node from the state local.db holds and the alerts its health keeps open."""

from p2pwatch.application.ports.driven.node_state_reader import NodeStateReader
from p2pwatch.application.ports.driven.open_alert_reader import OpenAlertReader
from p2pwatch.application.ports.driving.node_describer import NodeDescriber, NodeDescription


class DescribeNode(NodeDescriber):
    def __init__(
        self, *, node_state_reader: NodeStateReader, open_alert_reader: OpenAlertReader
    ) -> None:
        self._node_state_reader = node_state_reader
        self._open_alert_reader = open_alert_reader

    def describe_node(self) -> NodeDescription:
        return NodeDescription(
            node_state=self._node_state_reader.read_node_state(),
            open_alerts=self._open_alert_reader.read_open_alerts(),
        )
