"""``NodeDescriber``: describes the node, for its page."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from p2pwatch.domain.node_state import NodeState


@dataclass(frozen=True)
class NodeDescription:
    node_state: NodeState


class NodeDescriber(ABC):
    """Describes the node, from any thread."""

    @abstractmethod
    def describe_node(self) -> NodeDescription:
        """The node's identity, its tracked downloads and its search backoffs."""
