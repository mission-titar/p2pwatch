"""``NodeStateReader``: reads the node's own state, kept in local.db."""

from abc import ABC, abstractmethod

from p2pwatch.domain.node_state import NodeState


class NodeStateReader(ABC):
    """Reads the node's state from any thread."""

    @abstractmethod
    def read_node_state(self) -> NodeState:
        """Its downloads by when they were queued, then by native id; its backoffs by client, each
        client's whole-client backoff before its channels, then by channel."""
