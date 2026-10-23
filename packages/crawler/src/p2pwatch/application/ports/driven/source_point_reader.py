"""``SourcePointReader``: our downloads' sources as points (source points spec, D5);
synchronous, as the catalog's ports. Every point read is the ``node_id``'s the call gives."""

from abc import ABC, abstractmethod
from datetime import datetime

from p2pwatch.domain.source import LatestPoint, SourceKey


class SourcePointReader(ABC):
    """Reads the points observed before ``before``."""

    @abstractmethod
    def read_earlier_points(
        self, source: SourceKey, before: datetime, node_id: str
    ) -> tuple[LatestPoint, ...]:
        """The latest point of each of ``source``'s variants that has one before ``before``."""

    @abstractmethod
    def has_points_before(self, before: datetime, node_id: str) -> bool:
        """Whether any point was observed before ``before``."""
