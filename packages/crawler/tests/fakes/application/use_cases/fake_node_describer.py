from p2pwatch.application.ports.driving.node_describer import NodeDescriber, NodeDescription


class FakeNodeDescriber(NodeDescriber):
    """Describes the node as it is given."""

    def __init__(self, node_description: NodeDescription) -> None:
        self._node_description = node_description

    def describe_node(self) -> NodeDescription:
        return self._node_description
