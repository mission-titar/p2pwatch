"""``NodeIdReader``: reads the node's id, which ``local.db`` keeps from its first use."""

from abc import ABC, abstractmethod


class NodeIdReader(ABC):
    """Reads the node's id that ``local.db`` keeps."""

    @abstractmethod
    def read_node_id(self) -> str | None:
        """The stored id, ``None`` before one is recorded."""
