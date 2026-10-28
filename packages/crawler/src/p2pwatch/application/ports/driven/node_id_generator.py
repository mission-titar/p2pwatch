"""``NodeIdGenerator``: draws a new node's id."""

from abc import ABC, abstractmethod

from p2pwatch.domain.identifiers import NodeId


class NodeIdGenerator(ABC):
    """Draws a new node's id."""

    @abstractmethod
    def new_node_id(self) -> NodeId:
        """An id no other node draws."""
