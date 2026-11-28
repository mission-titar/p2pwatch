"""``NodeDescriber``: describes the node, for its page."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from p2pwatch.domain.health.external_dependency import HealthAlert
from p2pwatch.domain.node_state import NodeState


@dataclass(kw_only=True, frozen=True)
class NodeDescription:
    node_state: NodeState
    open_alerts: tuple[HealthAlert, ...]


class NodeDescriber(ABC):
    """Describes the node, from any thread."""

    @abstractmethod
    def describe_node(self) -> NodeDescription:
        """The node's identity, its tracked downloads, its search backoffs and its alerts open."""
