"""``SourcePointReader``: our downloads' sources as points (source points spec, D4, D5);
synchronous, as the catalog's ports. Every point read is the ``node_id``'s the call gives."""

from abc import ABC, abstractmethod
from datetime import datetime

from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.source import LatestPoint, SourceKey, SourceReading


class SourcePointReader(ABC):
    """Reads the points observed before ``before``."""

    @abstractmethod
    def read_latest_point(
        self,
        file: FileKey,
        *,
        reading: SourceReading,
        since: datetime,
        before: datetime,
        node_id: NodeId,
    ) -> LatestPoint | None:
        """The latest point of ``reading``'s source on ``file`` from ``since`` included to
        ``before`` excluded; a source without identity is its name among those without one."""

    @abstractmethod
    def read_earlier_points(
        self, source: SourceKey, *, before: datetime, node_id: NodeId
    ) -> tuple[LatestPoint, ...]:
        """The latest point of each of ``source``'s variants that has one before ``before``."""

    @abstractmethod
    def has_points_before(self, before: datetime, *, node_id: NodeId) -> bool:
        """Whether any point was observed before ``before``."""
