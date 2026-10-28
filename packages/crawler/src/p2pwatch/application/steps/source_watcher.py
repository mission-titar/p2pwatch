"""Reads the sources of our downloads, records their points and alerts."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.source_client import SourceClient
from p2pwatch.application.ports.driven.source_point_reader import SourcePointReader
from p2pwatch.application.ports.driven.source_point_writer import SourcePointWriter
from p2pwatch.application.ports.driven.tracked_download_reader import TrackedDownloadReader
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.download_labeler import DownloadLabeler
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.observability.events import SourceFirstUseful, SourceReappeared
from p2pwatch.domain.source import (
    EarlierPoints,
    SourceKey,
    SourcePoint,
    SourceReading,
    SourceRole,
    SourceUsefulness,
    carried_role,
    carried_role_max_age,
)
from p2pwatch.domain.source_alerts import FirstUseful, source_alert
from p2pwatch.domain.store_error import StoreError


@dataclass
class _AlertRound:
    """A round's alert state: the baseline is asked once, at the first useful reading with an id.
    A source decided once is decided for the round, since "earlier" excludes its points."""

    started_at: datetime
    decided: set[SourceKey] = field(default_factory=set)
    alerts_allowed: bool | None = None


class SourceWatcher:
    """Reads the sources of our downloads, records their points and alerts; owns the instant of
    its last read."""

    def __init__(
        self,
        *,
        source_client: SourceClient,
        tracked_download_reader: TrackedDownloadReader,
        source_point_writer: SourcePointWriter,
        source_point_reader: SourcePointReader,
        download_labeler: DownloadLabeler,
        reappeared_after: timedelta,
        sources_interval: timedelta,
        time_between_source_reads: timedelta,
        wall_clock: WallClock,
        monotonic_clock: MonotonicClock,
        observability_dispatcher: ObservabilityDispatcher,
        logger: Logger,
    ) -> None:
        self._source_client = source_client
        self._tracked_download_reader = tracked_download_reader
        self._source_point_writer = source_point_writer
        self._source_point_reader = source_point_reader
        self._download_labeler = download_labeler
        self._reappeared_after = reappeared_after
        self._sources_interval = sources_interval
        self._time_between_source_reads = time_between_source_reads
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._observability_dispatcher = observability_dispatcher
        self._logger = logger
        self._sources_read_at: MonotonicInstant | None = None

    async def record_sources(
        self, listed_statuses: tuple[DownloadStatus, ...], node_id: NodeId
    ) -> None:
        """Records the sources of each of our downloads the client lists, completed ones aside,
        then alerts on them (stage 4, D8; source points, D5). A store failure skips that
        download's; a client failure propagates.

        Runs once ``sources_interval`` has passed on the monotonic clock since its last start,
        failed or not (D3)."""
        started_at = self._monotonic_clock.now()
        last = self._sources_read_at
        if last is not None and started_at - last < self._sources_interval:
            return
        self._sources_read_at = started_at
        tracked = self._tracked_download_reader.read_tracked_states()
        round_ = _AlertRound(self._wall_clock.now())
        for status in listed_statuses:
            if status.completed or status.file not in tracked:
                continue
            read_at = self._wall_clock.now()
            readings = await self._source_client.sources(status.file)
            try:
                points = self._source_points(status.file, readings, read_at, node_id)
                self._source_point_writer.record_points(points)
                await self._alert_sources(status.file, points, round_, node_id)
            except StoreError as error:
                self._logger.error(
                    "sources file=%s store failure (%s): file skipped, continues",
                    status.file.native_id,
                    error,
                )

    def _source_points(
        self,
        file: FileKey,
        readings: tuple[SourceReading, ...],
        read_at: datetime,
        node_id: NodeId,
    ) -> tuple[SourcePoint, ...]:
        """A point per reading, with its role, the latest point's when aMule gives none; a source
        without identity is told apart by its name. Reads every latest point before the write,
        with no ``await`` between."""
        since = read_at - carried_role_max_age(self._time_between_source_reads)
        return tuple(
            SourcePoint(
                file, reading, self._role(file, reading, since, read_at, node_id), read_at, node_id
            )
            for reading in readings
            if reading.source is not None or reading.source_name is not None
        )

    def _role(
        self,
        file: FileKey,
        reading: SourceReading,
        since: datetime,
        read_at: datetime,
        node_id: NodeId,
    ) -> SourceRole:
        if reading.role is not None:
            return reading.role
        latest = self._source_point_reader.read_latest_point(file, reading, since, read_at, node_id)
        return carried_role(latest, reading)

    async def _alert_sources(
        self,
        file: FileKey,
        points: tuple[SourcePoint, ...],
        round_: _AlertRound,
        node_id: NodeId,
    ) -> None:
        """Emits D5's alerts for the useful points of a committed write, once per source per
        round."""
        for point in points:
            source = point.reading.source
            if source is None or point.role.usefulness is not SourceUsefulness.USEFUL:
                continue  # a name alone is too weak to carry an event
            if source in round_.decided:
                continue  # one event per source per round
            if round_.alerts_allowed is None:
                # The same answer at any point of the round: "before" excludes the round's writes.
                round_.alerts_allowed = self._source_point_reader.has_points_before(
                    round_.started_at, node_id
                )
            if not round_.alerts_allowed:
                return  # the node's first recording round is a baseline, not news
            earlier_points = EarlierPoints.of(
                self._source_point_reader.read_earlier_points(source, round_.started_at, node_id)
            )
            alert = source_alert(
                point.role, earlier_points, round_.started_at, self._reappeared_after
            )
            round_.decided.add(source)
            if alert is None:
                continue
            source_name = point.reading.source_name
            filename = self._download_labeler.best_filename(file)
            titles = self._download_labeler.target_titles(file)
            event: SourceFirstUseful | SourceReappeared = (
                SourceFirstUseful(source, source_name, file, filename, titles, node_id)
                if isinstance(alert, FirstUseful)
                else SourceReappeared(
                    source,
                    source_name,
                    file,
                    filename,
                    titles,
                    alert.absent_for.total_seconds(),
                    node_id,
                )
            )
            await self._observability_dispatcher.dispatch(event)
