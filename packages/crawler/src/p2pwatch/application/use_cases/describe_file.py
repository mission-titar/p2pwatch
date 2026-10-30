"""``DescribeFile``: a file's history and sharing periods over the requested interval, and why
its first decision holds against the current policy."""

from datetime import datetime, timedelta

from p2pwatch.application.ports.driven.catalog_file_reader import CatalogFileReader
from p2pwatch.application.ports.driven.source_reader import SourceReader
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.ports.driving.file_describer import FileDescriber, FileDescription
from p2pwatch.domain.identifiers import FileId
from p2pwatch.domain.interval import requested_interval
from p2pwatch.domain.matching_read import MatchingExplainer
from p2pwatch.domain.sharing_period import PeriodWindow


class DescribeFile(FileDescriber):
    def __init__(
        self,
        *,
        catalog_file_reader: CatalogFileReader,
        source_reader: SourceReader,
        explainer: MatchingExplainer,
        wall_clock: WallClock,
        source_period_gap: timedelta,
    ) -> None:
        self._catalog_file_reader = catalog_file_reader
        self._source_reader = source_reader
        self._explainer = explainer
        self._wall_clock = wall_clock
        self._source_period_gap = source_period_gap

    def describe_file(
        self,
        file_id: FileId,
        *,
        requested_since: datetime | None,
        requested_until: datetime | None,
    ) -> FileDescription | None:
        now = self._wall_clock.now().replace(microsecond=0)
        interval = requested_interval(requested_since, requested_until=requested_until, now=now)
        file_history = self._catalog_file_reader.read_file_history(
            file_id, since=interval.since, until=interval.until
        )
        if file_history is None:
            return None
        window = PeriodWindow(
            since=interval.since, until=interval.until, gap=self._source_period_gap
        )
        explanation = None
        latest = file_history.latest_observation
        if file_history.decisions and latest is not None:
            # Every known name with the latest fields, as the crawler judges.
            reported_file = latest.reported_file
            explanation = self._explainer.explain(
                filenames=file_history.known_filenames,
                size_bytes=reported_file.size_bytes,
                duration_seconds=reported_file.duration_seconds,
                bitrate_kbps=reported_file.bitrate_kbps,
                target_id=file_history.decisions[0].decision.target_id,
            )
        return FileDescription(
            file_history=file_history,
            sharing_periods=self._source_reader.read_sharing_periods(file_history.file, window),
            explanation=explanation,
            interval=interval,
            now=now,
        )
