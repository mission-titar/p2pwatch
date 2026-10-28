"""``NodeIdWriter``: records the node's id in ``local.db``, once."""

from abc import ABC, abstractmethod
from datetime import datetime

from p2pwatch.domain.identifiers import NodeId


class NodeIdWriter(ABC):
    """Records the node's id, once."""

    @abstractmethod
    def record_node_id(self, node_id: NodeId, created_at: datetime) -> None:
        """Stores ``node_id`` with its creation; a second one is refused (``StoreError``)."""
