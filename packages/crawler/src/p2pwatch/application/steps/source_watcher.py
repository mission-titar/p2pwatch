"""Source tracking, a work: reads the sources of our downloads, records their points and alerts.

Errors: an unavailable client skips the turn, a ``StoreError`` reading the tracked downloads fails
it, one writing a download's points skips that download's; the next turn retries.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from p2pwatch.application.ports.driven.download_client import DownloadClient
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.source_client import SourceClient
from p2pwatch.application.ports.driven.source_point_reader import SourcePointReader
from p2pwatch.application.ports.driven.source_point_writer import SourcePointWriter
from p2pwatch.application.ports.driven.tracked_download_reader import TrackedDownloadReader
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.download_labeler import DownloadLabeler
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.client_errors import ClientUnreachableError, ReadRejectedError
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.identifiers import ClientName, NodeId
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

# A read the client refuses is the daemon unavailable.
_UNAVAILABLE = (ClientUnreachableError, ReadRejectedError)


@dataclass(kw_only=True)
class _AlertRound:
    """A round's alert state: the baseline is asked once, at the first useful reading with an id.
    A source decided once is decided for the round, since "earlier" excludes its points."""

    started_at: datetime
    decided: set[SourceKey] = field(default_factory=set)
    alerts_allowed: bool | None = None


class SourceWatcher(Work):
    """Reads the sources of our downloads, records their points and alerts; owns the instant of
    its latest turn's start."""

    def __init__(
        self,
        *,
        client_name: ClientName,
        download_client: DownloadClient,
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
        node_id: NodeId,
        logger: Logger,
    ) -> None:
        self._client_name = client_name
        self._download_client = download_client
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
        self._node_id = node_id
        self._logger = logger
        self._turn_started_at: MonotonicInstant | None = None

    def __str__(self) -> str:
        return f"source tracking {self._client_name}"

    async def wait_for_next_turn(self) -> None:
        """Waits ``sources_interval`` since the latest turn started, failed or not (source points
        spec, D3), on the monotonic clock; nothing before the first."""
        if self._turn_started_at is None:
            return
        left = self._sources_interval - (self._monotonic_clock.now() - self._turn_started_at)
        if left > timedelta(0):
            await self._monotonic_clock.sleep(left)

    async def run_once(self) -> None:
        """Reads the client's downloads, then records and alerts on the sources of ours."""
        self._turn_started_at = self._monotonic_clock.now()  # first: a raising turn still waits
        try:
            await self._record_sources(await self._download_client.downloads())
        except _UNAVAILABLE as error:
            self._logger.warning("download daemon unreachable (%s): sources skipped, retry", error)

    async def _record_sources(self, listed_statuses: tuple[DownloadStatus, ...]) -> None:
        """Records the sources of each of our downloads the client lists, completed ones aside,
        then alerts on them (stage 4, D8; source points, D5). A store failure skips that
        download's; a client failure propagates."""
        tracked = self._tracked_download_reader.read_tracked_states()
        round_ = _AlertRound(started_at=self._wall_clock.now())
        for status in listed_statuses:
            if status.completed or status.file not in tracked:
                continue
            read_at = self._wall_clock.now()
            readings = await self._source_client.sources(status.file)
            try:
                points = self._source_points(status.file, readings=readings, read_at=read_at)
                self._source_point_writer.record_points(points)
                await self._alert_sources(status.file, points=points, round_=round_)
            except StoreError as error:
                self._logger.error(
                    "sources file=%s store failure (%s): file skipped, continues",
                    status.file.native_id,
                    error,
                )

    def _source_points(
        self,
        file: FileKey,
        *,
        readings: tuple[SourceReading, ...],
        read_at: datetime,
    ) -> tuple[SourcePoint, ...]:
        """A point per reading, with its role, the latest point's when aMule gives none; a source
        without identity is told apart by its name. Reads every latest point before the write,
        with no ``await`` between."""
        since = read_at - carried_role_max_age(self._time_between_source_reads)
        return tuple(
            SourcePoint(
                file=file,
                reading=reading,
                role=self._role(file, reading=reading, since=since, read_at=read_at),
                observed_at=read_at,
                node_id=self._node_id,
            )
            for reading in readings
            if reading.source is not None or reading.source_name is not None
        )

    def _role(
        self,
        file: FileKey,
        *,
        reading: SourceReading,
        since: datetime,
        read_at: datetime,
    ) -> SourceRole:
        if reading.role is not None:
            return reading.role
        latest = self._source_point_reader.read_latest_point(
            file, reading=reading, since=since, before=read_at, node_id=self._node_id
        )
        return carried_role(latest, reading=reading)

    async def _alert_sources(
        self,
        file: FileKey,
        *,
        points: tuple[SourcePoint, ...],
        round_: _AlertRound,
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
                    round_.started_at, node_id=self._node_id
                )
            if not round_.alerts_allowed:
                return  # the node's first recording round is a baseline, not news
            earlier_points = EarlierPoints.of(
                self._source_point_reader.read_earlier_points(
                    source, before=round_.started_at, node_id=self._node_id
                )
            )
            alert = source_alert(
                point.role,
                earlier_points=earlier_points,
                round_started_at=round_.started_at,
                reappeared_after=self._reappeared_after,
            )
            round_.decided.add(source)
            if alert is None:
                continue
            source_name = point.reading.source_name
            filename = self._download_labeler.best_filename(file)
            titles = self._download_labeler.target_titles(file)
            event: SourceFirstUseful | SourceReappeared = (
                SourceFirstUseful(
                    source=source,
                    source_name=source_name,
                    file=file,
                    filename=filename,
                    target_titles=titles,
                    node_id=self._node_id,
                )
                if isinstance(alert, FirstUseful)
                else SourceReappeared(
                    source=source,
                    source_name=source_name,
                    file=file,
                    filename=filename,
                    target_titles=titles,
                    absent_for_seconds=alert.absent_for.total_seconds(),
                    node_id=self._node_id,
                )
            )
            await self._observability_dispatcher.dispatch(event)
