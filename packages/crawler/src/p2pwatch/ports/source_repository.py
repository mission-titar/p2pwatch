"""``SourceRepository`` port: our downloads' sources, written as ranges (stage 4 spec, D4, D9).

SYNCHRONOUS, like ``CatalogRepository``. Every range read or written is this node's.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.source import SourceKey, SourceReading, SourceRole


@dataclass(frozen=True)
class OpenedRange:
    """A range ``record_readings`` opened, with its role, a carried one included."""

    key: SourceKey | None
    name: str | None
    role: SourceRole


@dataclass(frozen=True)
class EarlierRanges:
    """D9's two answers: a useful range exists, and when a useful or not-useful one last ended."""

    useful: bool
    last_known_at: datetime | None


class SourceRepository(Protocol):
    """``record_readings`` extends or opens each reading's range (D4) in one transaction; the
    reads count only the ranges that started before ``started_before``."""

    def record_readings(
        self,
        file: FileKey,
        readings: Sequence[SourceReading],
        read_at: datetime,
        tolerance: timedelta,
    ) -> tuple[OpenedRange, ...]: ...

    def earlier_ranges(self, source: SourceKey, started_before: datetime) -> EarlierRanges: ...

    def has_ranges_before(self, started_before: datetime) -> bool: ...
