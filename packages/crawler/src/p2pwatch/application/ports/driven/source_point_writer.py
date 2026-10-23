"""``SourcePointWriter``: our downloads' sources as points (source points spec, D4);
synchronous, as the catalog's ports. Every point written is the ``node_id``'s the call gives."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from p2pwatch.domain.source import SourcePoint


class SourcePointWriter(ABC):
    """Writes the points of our downloads' sources."""

    @abstractmethod
    def record_points(self, points: Sequence[SourcePoint], node_id: str) -> None:
        """Writes ``points`` (D4) in one transaction."""
