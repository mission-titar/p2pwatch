"""``NodeIdGenerator``: draws a new node's id."""

from abc import ABC, abstractmethod


class NodeIdGenerator(ABC):
    """Draws a new node's id."""

    @abstractmethod
    def new_node_id(self) -> str:
        """An id no other node draws."""
