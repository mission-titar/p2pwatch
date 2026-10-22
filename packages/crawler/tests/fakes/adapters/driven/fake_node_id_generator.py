from p2pwatch.application.ports.driven.node_id_generator import NodeIdGenerator


class FakeNodeIdGenerator(NodeIdGenerator):
    """Draws the one id it is given."""

    def __init__(self, node_id: str) -> None:
        self._node_id = node_id

    def new_node_id(self) -> str:
        return self._node_id
