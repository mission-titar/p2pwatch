"""Reads the sources of our downloads, records their points and alerts."""

from dataclasses import dataclass, field
from datetime import datetime

from p2pwatch.application.steps.download_deps import DownloadDeps
from p2pwatch.application.steps.download_file_reads import best_filename, target_titles
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey
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


def _source_points(
    deps: DownloadDeps,
    file: FileKey,
    readings: tuple[SourceReading, ...],
    read_at: datetime,
    node_id: str,
) -> tuple[SourcePoint, ...]:
    """Each reading a source or a name tells apart, with its role, a carried one included (D4).
    Reads every latest point before the write, with no ``await`` between."""
    since = read_at - carried_role_max_age(deps.time_between_source_reads)
    return tuple(
        SourcePoint(
            file, reading, _role(deps, file, reading, since, read_at, node_id), read_at, node_id
        )
        for reading in readings
        if reading.source is not None or reading.source_name is not None
    )


def _role(
    deps: DownloadDeps,
    file: FileKey,
    reading: SourceReading,
    since: datetime,
    read_at: datetime,
    node_id: str,
) -> SourceRole:
    if reading.role is not None:
        return reading.role
    latest = deps.source_point_reader.read_latest_point(file, reading, since, read_at, node_id)
    return carried_role(latest, reading)


async def _alert_sources(
    deps: DownloadDeps,
    file: FileKey,
    points: tuple[SourcePoint, ...],
    round_: _AlertRound,
    node_id: str,
) -> None:
    """Emits D5's alerts for the useful points of a committed write, once per source per round."""
    for point in points:
        source = point.reading.source
        if source is None or point.role.usefulness is not SourceUsefulness.USEFUL:
            continue  # a name alone is too weak to carry an event
        if source in round_.decided:
            continue  # one event per source per round
        if round_.alerts_allowed is None:
            # The same answer at any point of the round: "before" excludes the round's writes.
            round_.alerts_allowed = deps.source_point_reader.has_points_before(
                round_.started_at, node_id
            )
        if not round_.alerts_allowed:
            return  # the node's first recording round is a baseline, not news
        earlier_points = EarlierPoints.of(
            deps.source_point_reader.read_earlier_points(source, round_.started_at, node_id)
        )
        alert = source_alert(point.role, earlier_points, round_.started_at, deps.reappeared_after)
        round_.decided.add(source)
        if alert is None:
            continue
        source_name, filename = point.reading.source_name, best_filename(deps, file)
        titles = target_titles(deps, file)
        event: SourceFirstUseful | SourceReappeared = (
            SourceFirstUseful(source, source_name, file, filename, titles)
            if isinstance(alert, FirstUseful)
            else SourceReappeared(
                source, source_name, file, filename, titles, alert.absent_for.total_seconds()
            )
        )
        await deps.observability_dispatcher.dispatch(event, node_id)


async def record_sources(
    deps: DownloadDeps, listed_statuses: tuple[DownloadStatus, ...], node_id: str
) -> None:
    """Records the sources of each of our downloads the client lists, completed ones aside, then
    alerts on them (stage 4, D8; source points, D5). A store failure skips that download's; a
    client failure propagates.

    Runs once ``sources_interval`` has passed on the monotonic clock since its last start, failed
    or not (D3)."""
    started_at = deps.monotonic_clock.now()
    last = deps.sources_read_at
    if last is not None and started_at - last < deps.sources_interval:
        return
    deps.sources_read_at = started_at
    tracked = deps.tracked_download_reader.read_tracked_states()
    round_ = _AlertRound(deps.wall_clock.now())
    for status in listed_statuses:
        if status.completed or status.file not in tracked:
            continue
        read_at = deps.wall_clock.now()
        readings = await deps.source_client.sources(status.file)
        try:
            points = _source_points(deps, status.file, readings, read_at, node_id)
            deps.source_point_writer.record_points(points)
            await _alert_sources(deps, status.file, points, round_, node_id)
        except StoreError as error:
            deps.logger.error(
                "sources file=%s store failure (%s): file skipped, continues",
                status.file.native_id,
                error,
            )
