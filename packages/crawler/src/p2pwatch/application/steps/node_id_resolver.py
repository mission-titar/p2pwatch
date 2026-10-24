"""The node's id: the one ``crawler.yml`` configures, else the one ``local.db`` holds."""

from p2pwatch.application.ports.driven.node_id_generator import NodeIdGenerator
from p2pwatch.application.ports.driven.node_id_reader import NodeIdReader
from p2pwatch.application.ports.driven.node_id_writer import NodeIdWriter
from p2pwatch.application.ports.driven.wall_clock import WallClock


class NodeIdResolver:
    """Resolves the id the node runs under, once at its start."""

    def __init__(
        self,
        *,
        configured_node_id: str | None,
        node_id_reader: NodeIdReader,
        node_id_writer: NodeIdWriter,
        node_id_generator: NodeIdGenerator,
        wall_clock: WallClock,
    ) -> None:
        self._configured_node_id = configured_node_id
        self._node_id_reader = node_id_reader
        self._node_id_writer = node_id_writer
        self._node_id_generator = node_id_generator
        self._wall_clock = wall_clock

    def resolve(self) -> str:
        """The configured ``node_id`` if any, else the stored one, else a new one, recorded."""
        if self._configured_node_id is not None:
            return self._configured_node_id
        stored_node_id = self._node_id_reader.read_node_id()
        if stored_node_id is not None:
            return stored_node_id
        node_id = self._node_id_generator.new_node_id()
        self._node_id_writer.record_node_id(node_id, self._wall_clock.now())
        return node_id
