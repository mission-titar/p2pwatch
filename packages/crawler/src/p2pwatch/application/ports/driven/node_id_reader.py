"""``NodeIdReader``: reads the node's id, which ``local.db`` keeps from its first use."""

from abc import ABC, abstractmethod

from p2pwatch.domain.identifiers import NodeId


class NodeIdReader(ABC):
    """Reads the node's id that ``local.db`` keeps."""

    @abstractmethod
    def read_node_id(self) -> NodeId | None:
        """The stored id, ``None`` before one is recorded."""
