"""Describes the node from the state local.db holds."""

from p2pwatch.ports.driven.node_state_reader import NodeStateReader
from p2pwatch.ports.driving.node_describer import NodeDescriber, NodeDescription


class DescribeNode(NodeDescriber):
    def __init__(self, node_state_reader: NodeStateReader) -> None:
        self._node_state_reader = node_state_reader

    def describe_node(self) -> NodeDescription:
        return NodeDescription(node_state=self._node_state_reader.read_node_state())
