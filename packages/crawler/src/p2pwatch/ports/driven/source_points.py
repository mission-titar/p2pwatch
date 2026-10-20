"""Our downloads' sources as points (source points spec, D4, D5).

SYNCHRONOUS, like the catalog's ports. Every point read or written is the ``node_id``'s the call
gives.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.source import SourceKey, SourceReading, SourceRole


@dataclass(frozen=True)
class RecordedReading:
    """A reading ``record_readings`` kept, with its role, a carried one included."""

    source: SourceKey | None
    source_name: str | None
    role: SourceRole


@dataclass(frozen=True)
class EarlierPoints:
    """D5's two answers: a useful point exists, and when the latest useful or not-useful one was."""

    has_useful_point: bool
    latest_known_at: datetime | None


class SourcePointWriter(ABC):
    """Writes the points of our downloads' sources."""

    @abstractmethod
    def record_readings(
        self, file: FileKey, readings: Sequence[SourceReading], read_at: datetime, node_id: str
    ) -> tuple[RecordedReading, ...]:
        """Writes one point per reading (D4) in one transaction."""


class SourcePointReader(ABC):
    """Reads the points observed before ``before``."""

    @abstractmethod
    def read_earlier_points(
        self, source: SourceKey, before: datetime, node_id: str
    ) -> EarlierPoints:
        """D5's two answers for ``source``."""

    @abstractmethod
    def has_points_before(self, before: datetime, node_id: str) -> bool:
        """Whether any point was observed before ``before``."""
