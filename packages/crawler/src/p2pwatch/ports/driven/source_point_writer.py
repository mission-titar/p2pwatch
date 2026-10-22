"""``SourcePointWriter``: our downloads' sources as points (source points spec, D4);
synchronous, as the catalog's ports. Every point written is the ``node_id``'s the call gives."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime

from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.source import RecordedReading, SourceReading


class SourcePointWriter(ABC):
    """Writes the points of our downloads' sources."""

    @abstractmethod
    def record_readings(
        self, file: FileKey, readings: Sequence[SourceReading], read_at: datetime, node_id: str
    ) -> tuple[RecordedReading, ...]:
        """Writes one point per reading (D4) in one transaction."""
