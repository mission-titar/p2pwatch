from datetime import datetime

from p2pwatch.application.ports.driven.node_id_reader import NodeIdReader
from p2pwatch.application.ports.driven.node_id_writer import NodeIdWriter
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.store_error import StoreError


class FakeNodeIdStore(NodeIdReader, NodeIdWriter):
    """The node's id in memory: keeps the id recorded with its instant."""

    def __init__(self, *, stored_node_id: NodeId | None) -> None:
        self._stored_node_id = stored_node_id
        self.recorded: list[tuple[NodeId, datetime]] = []

    def read_node_id(self) -> NodeId | None:
        return self._stored_node_id

    def record_node_id(self, node_id: NodeId, *, created_at: datetime) -> None:
        if self._stored_node_id is not None:
            raise StoreError(f"a node id is already recorded: {self._stored_node_id}")
        self.recorded.append((node_id, created_at))
        self._stored_node_id = node_id
