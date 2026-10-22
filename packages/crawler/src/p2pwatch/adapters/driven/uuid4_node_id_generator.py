"""``Uuid4NodeIdGenerator``: a new node's id, a random UUID."""

import uuid

from p2pwatch.ports.driven.node_id_generator import NodeIdGenerator


class Uuid4NodeIdGenerator(NodeIdGenerator):
    """Draws each id from ``uuid.uuid4``, so no two nodes share one."""

    def new_node_id(self) -> str:
        return str(uuid.uuid4())
