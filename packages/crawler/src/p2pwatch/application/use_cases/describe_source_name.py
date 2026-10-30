"""``DescribeSourceName``: a page of the sources that carried a name and its sharing periods
without a user hash over the requested interval."""

from datetime import datetime, timedelta

from p2pwatch.application.ports.driven.source_reader import SourceReader
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.ports.driving.source_name_describer import (
    SourceNameDescriber,
    SourceNameDescription,
)
from p2pwatch.application.use_cases.paging import PAGE_SIZE
from p2pwatch.domain.interval import requested_interval
from p2pwatch.domain.sharing_period import PeriodWindow


class DescribeSourceName(SourceNameDescriber):
    def __init__(
        self, *, source_reader: SourceReader, wall_clock: WallClock, source_period_gap: timedelta
    ) -> None:
        self._source_reader = source_reader
        self._wall_clock = wall_clock
        self._source_period_gap = source_period_gap

    def describe_source_name(
        self,
        source_name: str,
        *,
        page: int,
        requested_since: datetime | None,
        requested_until: datetime | None,
    ) -> SourceNameDescription | None:
        now = self._wall_clock.now().replace(microsecond=0)
        interval = requested_interval(requested_since, requested_until=requested_until, now=now)
        source_name_history = self._source_reader.read_source_name_history(
            source_name,
            limit=PAGE_SIZE,
            offset=(page - 1) * PAGE_SIZE,
            window=PeriodWindow(interval.since, interval.until, self._source_period_gap),
        )
        if source_name_history is None:
            return None
        return SourceNameDescription(
            source_name_history=source_name_history,
            # A full page offers the next one, even when it turns out empty.
            has_next_page=len(source_name_history.source_namings) >= PAGE_SIZE,
            interval=interval,
            now=now,
        )
