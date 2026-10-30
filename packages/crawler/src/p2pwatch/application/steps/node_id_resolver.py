"""The node's id: the one ``local.db`` holds, else a new one it records."""

from p2pwatch.application.ports.driven.node_id_generator import NodeIdGenerator
from p2pwatch.application.ports.driven.node_id_reader import NodeIdReader
from p2pwatch.application.ports.driven.node_id_writer import NodeIdWriter
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.domain.identifiers import NodeId


class NodeIdResolver:
    """Resolves the id the node runs under, once at its start."""

    def __init__(
        self,
        *,
        node_id_reader: NodeIdReader,
        node_id_writer: NodeIdWriter,
        node_id_generator: NodeIdGenerator,
        wall_clock: WallClock,
    ) -> None:
        self._node_id_reader = node_id_reader
        self._node_id_writer = node_id_writer
        self._node_id_generator = node_id_generator
        self._wall_clock = wall_clock

    def resolve(self) -> NodeId:
        """The stored ``node_id``, else a new one, recorded."""
        stored_node_id = self._node_id_reader.read_node_id()
        if stored_node_id is not None:
            return stored_node_id
        node_id = self._node_id_generator.new_node_id()
        self._node_id_writer.record_node_id(node_id, created_at=self._wall_clock.now())
        return node_id
