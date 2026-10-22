from p2pwatch.application.ports.driven.node_state_reader import NodeStateReader
from p2pwatch.domain.node_state import NodeState


class FakeNodeStateReader(NodeStateReader):
    """Reads the state it is given."""

    def __init__(self, node_state: NodeState) -> None:
        self._node_state = node_state

    def read_node_state(self) -> NodeState:
        return self._node_state
