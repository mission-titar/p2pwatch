from p2pwatch.application.ports.driven.node_id_generator import NodeIdGenerator
from p2pwatch.domain.identifiers import NodeId


class FakeNodeIdGenerator(NodeIdGenerator):
    """Draws the one id it is given."""

    def __init__(self, node_id: NodeId) -> None:
        self._node_id = node_id

    def new_node_id(self) -> NodeId:
        return self._node_id
