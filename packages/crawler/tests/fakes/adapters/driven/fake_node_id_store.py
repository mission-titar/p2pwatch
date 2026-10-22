from datetime import datetime

from p2pwatch.application.ports.driven.node_id_reader import NodeIdReader
from p2pwatch.application.ports.driven.node_id_writer import NodeIdWriter


class FakeNodeIdStore(NodeIdReader, NodeIdWriter):
    """``local.db``'s node id: counts its reads, keeps each id recorded with its instant."""

    def __init__(self, *, stored_node_id: str | None) -> None:
        self._stored_node_id = stored_node_id
        self.reads = 0
        self.recorded: list[tuple[str, datetime]] = []

    def read_node_id(self) -> str | None:
        self.reads += 1
        return self._stored_node_id

    def record_node_id(self, node_id: str, created_at: datetime) -> None:
        self.recorded.append((node_id, created_at))
        self._stored_node_id = node_id
