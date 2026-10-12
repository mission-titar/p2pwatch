"""``SourceRepository`` port: our downloads' sources, kept as ranges (stage 4 spec, D4, D9).

SYNCHRONOUS, like ``CatalogRepository``. Every range read is this node's.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from p2pwatch.domain.source import SourceKey


@dataclass(frozen=True)
class EarlierRanges:
    """D9's two answers: a useful range exists, and when a useful or not-useful one last ended."""

    useful: bool
    last_known_at: datetime | None


class SourceRepository(Protocol):
    """The reads count only the ranges that started before ``started_before``."""

    def earlier_ranges(self, source: SourceKey, started_before: datetime) -> EarlierRanges: ...

    def has_ranges_before(self, started_before: datetime) -> bool: ...
