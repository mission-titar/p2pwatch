"""The node's id: ``local.db`` keeps the one created on first use, ``NodeIdGenerator`` draws it."""

from abc import ABC, abstractmethod
from datetime import datetime


class NodeIdReader(ABC):
    """Reads the node's id that ``local.db`` keeps."""

    @abstractmethod
    def read_node_id(self) -> str | None:
        """The stored id, ``None`` before one is recorded."""


class NodeIdWriter(ABC):
    """Records the node's id, once."""

    @abstractmethod
    def record_node_id(self, node_id: str, created_at: datetime) -> None:
        """Stores ``node_id`` with its creation; a second one is refused (``RepositoryError``)."""


class NodeIdGenerator(ABC):
    """Draws a new node's id."""

    @abstractmethod
    def new_node_id(self) -> str:
        """An id no other node draws."""
