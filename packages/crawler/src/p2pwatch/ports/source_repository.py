"""``SourceRepository`` port: our downloads' sources as points (source points spec, D4, D5).

SYNCHRONOUS, like ``CatalogRepository``. Every point read or written is this node's.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.source import SourceKey, SourceReading, SourceRole


@dataclass(frozen=True)
class RecordedReading:
    """A reading ``record_readings`` kept, with its role, a carried one included."""

    key: SourceKey | None
    name: str | None
    role: SourceRole


@dataclass(frozen=True)
class EarlierPoints:
    """D5's two answers: a useful point exists, and when the latest useful or not-useful one was."""

    useful: bool
    last_known_at: datetime | None


class SourceRepository(Protocol):
    """``record_readings`` writes one point per reading (D4) in one transaction; the reads count
    only the points observed before ``before``."""

    def record_readings(
        self, file: FileKey, readings: Sequence[SourceReading], read_at: datetime
    ) -> tuple[RecordedReading, ...]: ...

    def earlier_points(self, source: SourceKey, before: datetime) -> EarlierPoints: ...

    def has_points_before(self, before: datetime) -> bool: ...
