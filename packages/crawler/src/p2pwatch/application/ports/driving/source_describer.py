"""``SourceDescriber``: describes one source over an interval, for its page."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from p2pwatch.domain.interval import Interval
from p2pwatch.domain.source_history import SourceHistory


@dataclass(frozen=True)
class SourceDescription:
    source_history: SourceHistory  # its names on the page asked for
    has_next_page: bool  # the page of names is full, so the next one may hold more
    interval: Interval  # the one read, resolved from the request
    now: datetime  # to the second: the interval's presets end there


class SourceDescriber(ABC):
    """Describes a source from any thread."""

    @abstractmethod
    def describe_source(
        self,
        source_id: bytes,
        *,
        page: int,
        requested_since: datetime | None,
        requested_until: datetime | None,
    ) -> SourceDescription | None:
        """The ``page``-th page (from 1) of the source's names, and its periods over the interval
        requested; ``None`` for a source the catalog never recorded."""
