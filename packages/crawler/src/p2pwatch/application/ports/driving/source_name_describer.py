"""``SourceNameDescriber``: describes one source name over an interval, for its page."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from p2pwatch.domain.interval import Interval
from p2pwatch.domain.source_history import SourceNameHistory


@dataclass(kw_only=True, frozen=True)
class SourceNameDescription:
    source_name_history: SourceNameHistory  # its sources on the page asked for
    has_next_page: bool  # the page of sources is full, so the next one may hold more
    interval: Interval  # the one read, resolved from the request
    now: datetime  # to the second: the interval's presets end there


class SourceNameDescriber(ABC):
    """Describes a source name from any thread."""

    @abstractmethod
    def describe_source_name(
        self,
        source_name: str,
        *,
        page: int,
        requested_since: datetime | None,
        requested_until: datetime | None,
    ) -> SourceNameDescription | None:
        """The ``page``-th page (from 1) of the sources that carried the name, and its periods
        without a user hash over the interval requested; ``None`` for a name never recorded."""
