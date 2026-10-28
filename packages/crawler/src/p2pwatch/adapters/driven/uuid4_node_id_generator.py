"""``Uuid4NodeIdGenerator``: a new node's id, a random UUID."""

import uuid

from p2pwatch.application.ports.driven.node_id_generator import NodeIdGenerator
from p2pwatch.domain.identifiers import NodeId


class Uuid4NodeIdGenerator(NodeIdGenerator):
    """Draws each id from ``uuid.uuid4``, so no two nodes share one."""

    def new_node_id(self) -> NodeId:
        return NodeId(str(uuid.uuid4()))
