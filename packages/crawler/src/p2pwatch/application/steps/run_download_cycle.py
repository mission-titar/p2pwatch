"""The download loop: reconcile → completions → new candidates → sources → sleep/wake (spec §5).

One serial task. ``run_download_cycle`` runs ONE iteration;
``download_loop`` repeats it until shutdown, waiting ``poll_interval`` or the download wake.
Three things in it are not obvious:

- **A completion is the client's own signal, never the bytes** (2026-09-02: 065B was stamped
  complete at 20.1 %). ``DownloadStatus.completed`` carries it.
- **A download's absence is measured on the monotonic clock** (monotonic clock spec, D7).
  ``latest_seen_at`` only carries it across a restart, clamped by ``remaining_wait``: a wall-clock
  step fails nothing.
- **A download the client does not list is started again**, once per round, until it is listed
  or the TTL fails it: a client may forget its transfers on restart.

Errors: ``ClientUnreachableError``, a refused read and ``OSError`` on the disk measurement skip
the iteration, ``StoreError`` is logged and the cycle continues. A stalled download is never
abandoned.
"""

import asyncio
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from catalog_matching.domain.models import TargetSegment
from p2pwatch.application.ports.driven.decision_reader import DecisionReader
from p2pwatch.application.ports.driven.download_client import DownloadClient
from p2pwatch.application.ports.driven.event_emitter import EventEmitter
from p2pwatch.application.ports.driven.free_space_meter import FreeSpaceMeter
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.observation_reader import ObservationReader
from p2pwatch.application.ports.driven.source_client import SourceClient
from p2pwatch.application.ports.driven.source_point_reader import SourcePointReader
from p2pwatch.application.ports.driven.source_point_writer import SourcePointWriter
from p2pwatch.application.ports.driven.tracked_download_reader import TrackedDownloadReader
from p2pwatch.application.ports.driven.tracked_download_writer import TrackedDownloadWriter
from p2pwatch.application.ports.driven.waker import Waker
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.domain.client_errors import ClientUnreachableError, DownloadRejectedError
from p2pwatch.domain.download.policy import DownloadVerdict, decide_download
from p2pwatch.domain.download.request import DownloadRequest
from p2pwatch.domain.download.states import DownloadState, FailureReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.edge_state import EdgeState
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.observability.events import (
    DiskSpaceLow,
    DownloadCompleted,
    DownloadQueued,
    FreeSpaceSampled,
    SourceFirstUseful,
    SourceReappeared,
    TargetTitle,
)
from p2pwatch.domain.persisted_wait import remaining_wait
from p2pwatch.domain.source import RecordedReading, SourceKey, SourceUsefulness
from p2pwatch.domain.source_alerts import FirstUseful, source_alert
from p2pwatch.domain.store_error import StoreError

# Conventional subject of the download wake (DECISION D13). D-download subscribes to THIS
# subject; the producer side (the pipeline) calls wake("download").
DOWNLOAD_WAKE_SUBJECT = "download"

# A read the client refuses (amuleapi's ``amuled_rejected``) is the daemon unavailable.
_UNAVAILABLE = (ClientUnreachableError, DownloadRejectedError)


@dataclass
class DownloadDeps:
    """Dependencies of the download loop (composition assembles them once).

    ``targets`` serves the ``target_id → status`` lookup (pure policy). ``free_space_meter``
    measures the free space of the filesystem the client writes to (metadata only, no file is
    opened).
    """

    download_client: DownloadClient
    source_client: SourceClient
    tracked_download_writer: TrackedDownloadWriter
    tracked_download_reader: TrackedDownloadReader
    source_point_writer: SourcePointWriter
    source_point_reader: SourcePointReader
    decision_reader: DecisionReader
    observation_reader: ObservationReader
    targets: Sequence[TargetSegment]
    free_space_meter: FreeSpaceMeter
    min_free_bytes: int
    lost_after: timedelta
    poll_interval_seconds: float
    reappeared_after: timedelta
    sources_interval: timedelta
    wall_clock: WallClock
    monotonic_clock: MonotonicClock
    event_emitter: EventEmitter
    logger: Logger
    disk_low_edge: EdgeState = field(default_factory=EdgeState, kw_only=True)  # low-disk warning
    # The sources step's last start.
    sources_read_at: MonotonicInstant | None = field(default=None, kw_only=True)
    # Each queued or downloading download's instant from which it counts as lost.
    loss_deadline_by_file: dict[FileKey, MonotonicInstant] = field(
        default_factory=dict, kw_only=True
    )


@dataclass
class DownloadLoopDeps(DownloadDeps):
    """``DownloadDeps`` + what it takes to REPEAT (waker, shutdown) - DECISION D12."""

    waker: Waker
    shutdown: asyncio.Event


def _target_status(targets: Sequence[TargetSegment], target_id: str) -> str:
    """Target status (lookup ``target_id → status``); ``complete`` by default if the target
    has vanished from the config (conservative: do not download for an unknown target)."""
    for target in targets:
        if target.target_id == target_id:
            return target.status
    return "complete"


async def _reconcile_states(
    deps: DownloadDeps,
    states: dict[FileKey, DownloadState],
    listed_statuses: tuple[DownloadStatus, ...],
) -> None:
    """Reconciles ``downloads`` with the client's list: a failure it reports, else DOWNLOADING.

    ``FAILED`` is a wall only while the client reports a failure, so an erroneous download does
    not flap back each round; ``COMPLETED`` is one, so its notification never fires twice.
    """
    for status in listed_statuses:
        file = status.file
        current = states.get(file)
        if current is None:
            continue  # download outside the crawler: ignored
        if current is DownloadState.COMPLETED:
            continue  # already notified: don't regress and don't re-fire
        failed = status.failure_reason is not None
        wanted_state: Literal[DownloadState.DOWNLOADING, DownloadState.FAILED] = (
            DownloadState.FAILED if failed else DownloadState.DOWNLOADING
        )
        if current is not wanted_state:
            deps.tracked_download_writer.set_state(file, wanted_state, status.failure_reason)
            states[file] = wanted_state


def _target_titles(deps: DownloadDeps, file: FileKey) -> tuple[TargetTitle, ...]:
    """Every download target of the file, else the one it was queued for (the decision may have
    dropped since), each with its title."""
    target_ids = [
        c.target_id for c in deps.decision_reader.read_download_candidates() if c.file == file
    ]
    if (
        not target_ids
        and (queued := deps.tracked_download_reader.read_queued_target_id(file)) is not None
    ):
        target_ids = [queued]
    titles = {target.target_id: target.title for target in deps.targets}
    return tuple(TargetTitle(target_id, titles.get(target_id, "")) for target_id in target_ids)


def _best_filename(deps: DownloadDeps, file: FileKey) -> str:
    """The clean filename; the native id names a file whose observations are gone."""
    best = deps.observation_reader.read_best_observation(file)
    return file.native_id if best is None else best.reported_file.filename


async def _record_completion(
    deps: DownloadDeps, file: FileKey, states: dict[FileKey, DownloadState], node_id: str
) -> None:
    """Marks ``completed`` (stamps completed_at) and notifies (step 2, §5).

    ``completed`` is terminal: the file stays where the client put it, nothing moves it and
    nothing opens it. The caller skips files already ``completed``, so the notification fires
    exactly once per download.
    """
    deps.tracked_download_writer.set_completed(file, deps.wall_clock.now())
    states[file] = DownloadState.COMPLETED
    await deps.event_emitter.emit(
        DownloadCompleted(
            file,
            _best_filename(deps, file),
            _target_titles(deps, file) or (TargetTitle("unknown", ""),),
        ),
        node_id,
    )
    deps.logger.info("file=%s completed", file.native_id)


async def _handle_completions(
    deps: DownloadDeps,
    states: dict[FileKey, DownloadState],
    listed_statuses: tuple[DownloadStatus, ...],
    node_id: str,
) -> None:
    """Completes each tracked file the client reports ``completed``.

    A ``failed`` file completes too: the TTL can condemn a download that had in fact finished.
    A store failure on one file skips that file only.
    """
    for status in listed_statuses:
        file = status.file
        current = states.get(file)
        if not status.completed or current is None:
            continue  # not completed, or a download outside the crawler: ignored
        if current is DownloadState.COMPLETED:
            continue  # already completed: the notification fired once
        try:
            await _record_completion(deps, file, states, node_id)
        except StoreError as error:
            deps.logger.error(
                "completion file=%s store failure (%s): file skipped, continues",
                file.native_id,
                error,
            )


def _reconcile_loss_deadlines(
    deps: DownloadDeps, listed_files: frozenset[FileKey], monotonic_now: MonotonicInstant
) -> None:
    """Gives each queued or downloading download its loss deadline: ``lost_after`` from now if
    listed, else the one held, else what its ``latest_seen_at`` leaves."""
    deadlines = deps.loss_deadline_by_file
    latest_seen_at_by_file = deps.tracked_download_reader.read_latest_seen_at_by_file()
    for file in deadlines.keys() - latest_seen_at_by_file.keys():
        del deadlines[file]  # terminal now, or a row the operator deleted for a manual retry
    for file, latest_seen_at in latest_seen_at_by_file.items():
        if file in listed_files:
            deadlines[file] = monotonic_now + deps.lost_after
        elif file not in deadlines:
            left = remaining_wait(latest_seen_at, deps.lost_after, deps.wall_clock.now())
            deadlines[file] = monotonic_now + left


def _fail_lost(deps: DownloadDeps, listed_files: frozenset[FileKey]) -> None:
    """Fails each download the client has not listed for ``lost_after``.

    It bounds a client that accepts ``start()`` without ever listing the download.
    ``is_tracked`` stays state-blind, so a ``failed`` row still blocks automatic re-queuing;
    the manual retry is deleting the row.
    """
    monotonic_now = deps.monotonic_clock.now()
    _reconcile_loss_deadlines(deps, listed_files, monotonic_now)
    deadlines = deps.loss_deadline_by_file
    for file in [file for file, deadline in deadlines.items() if deadline <= monotonic_now]:
        deps.tracked_download_writer.set_state(file, DownloadState.FAILED, FailureReason.LOST)
        del deadlines[file]
        deps.logger.warning(
            "file=%s unseen by the client for %ss: marked failed",
            file.native_id,
            deps.lost_after.total_seconds(),
        )


async def _queue_new_candidates(deps: DownloadDeps, outstanding_bytes: int, node_id: str) -> None:
    """Replays tier=download decisions missing from ``downloads`` (step 3, spec §5).

    ``outstanding_bytes`` is what the client still has to transfer, measured from the cycle's
    snapshot; ``free_bytes`` is read once here. Both are MEASURED, never declared.
    """
    free_bytes = deps.free_space_meter.free_bytes()
    await deps.event_emitter.emit(FreeSpaceSampled(free_bytes=free_bytes), node_id)
    if free_bytes >= deps.min_free_bytes:
        deps.disk_low_edge.leave("disk_low")
    elif deps.disk_low_edge.enter("disk_low"):
        await deps.event_emitter.emit(
            DiskSpaceLow(free_bytes=free_bytes, min_free_bytes=deps.min_free_bytes), node_id
        )
    for candidate in deps.decision_reader.read_download_candidates():
        if deps.tracked_download_reader.is_tracked(candidate.file):
            continue
        observation = deps.observation_reader.read_latest_observation(candidate.file)
        if observation is None:
            deps.logger.warning(
                "candidate file=%s without observation: link impossible, skipped",
                candidate.file.native_id,
            )
            continue
        size_bytes = observation.reported_file.size_bytes
        verdict = decide_download(
            tier="download",
            target_status=_target_status(deps.targets, candidate.target_id),
            already_tracked=False,
            free_bytes=free_bytes,
            outstanding_bytes=outstanding_bytes,
            size_bytes=size_bytes,
            min_free_bytes=deps.min_free_bytes,
        )
        if verdict is not DownloadVerdict.DOWNLOAD:
            deps.logger.info(
                "candidate file=%s → %s (skipped/deferred)", candidate.file.native_id, verdict.value
            )
            continue
        # record_queued ONLY here (sync DB write); _start_unlisted sends it (network I/O): the
        # write precedes the network, and a start that raises leaves it 'queued' for next round.
        if deps.tracked_download_writer.record_queued(
            candidate.file, candidate.target_id, size_bytes, deps.wall_clock.now()
        ):
            deadline = deps.monotonic_clock.now() + deps.lost_after
            deps.loss_deadline_by_file[candidate.file] = deadline
        outstanding_bytes += size_bytes  # the client does not list it yet
        deps.logger.info("candidate file=%s queued for download", candidate.file.native_id)
        await deps.event_emitter.emit(DownloadQueued(target_id=candidate.target_id), node_id)


async def _start_unlisted(deps: DownloadDeps, listed_files: frozenset[FileKey]) -> None:
    """Starts every ``queued`` or ``downloading`` download the client does not list (D13).

    A new download and a forgotten one are the same case. ``DownloadRejectedError`` fails THAT
    download, since retrying would resend a refused request; ``ClientUnreachableError``
    propagates and the caller skips the iteration.
    """
    # FRESH re-read: _queue_new_candidates wrote new QUEUED rows this cycle.
    states = deps.tracked_download_reader.read_tracked_states()
    for file, state in states.items():
        if state not in {DownloadState.QUEUED, DownloadState.DOWNLOADING} or file in listed_files:
            continue
        observation = deps.observation_reader.read_latest_observation(file)
        if observation is None:
            continue
        reported_file = observation.reported_file
        try:
            await deps.download_client.start(
                DownloadRequest(file, reported_file.filename, reported_file.size_bytes)
            )
        except DownloadRejectedError as error:
            deps.tracked_download_writer.set_state(
                file, DownloadState.FAILED, FailureReason.REJECTED
            )
            deps.logger.warning(
                "start rejected by the client for file=%s (%s): marked failed",
                file.native_id,
                error,
            )


@dataclass
class _AlertRound:
    """A round's alert state: the baseline is asked once, at the first useful reading with an id.
    A source decided once is decided for the round, since "earlier" excludes its points."""

    started_at: datetime
    decided: set[SourceKey] = field(default_factory=set)
    alerts_allowed: bool | None = None


async def _alert_sources(
    deps: DownloadDeps,
    file: FileKey,
    recorded: tuple[RecordedReading, ...],
    round_: _AlertRound,
    node_id: str,
) -> None:
    """Emits D5's alerts for the useful readings of a committed write, once per source per round."""
    for reading in recorded:
        source = reading.source
        if source is None or reading.role.usefulness is not SourceUsefulness.USEFUL:
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
        earlier_points = deps.source_point_reader.read_earlier_points(
            source, round_.started_at, node_id
        )
        alert = source_alert(reading.role, earlier_points, round_.started_at, deps.reappeared_after)
        round_.decided.add(source)
        if alert is None:
            continue
        source_name, filename = reading.source_name, _best_filename(deps, file)
        target_titles = _target_titles(deps, file)
        event: SourceFirstUseful | SourceReappeared = (
            SourceFirstUseful(source, source_name, file, filename, target_titles)
            if isinstance(alert, FirstUseful)
            else SourceReappeared(
                source, source_name, file, filename, target_titles, alert.absent_for.total_seconds()
            )
        )
        await deps.event_emitter.emit(event, node_id)


async def _record_sources(
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
            recorded = deps.source_point_writer.record_readings(
                status.file, readings, read_at, node_id
            )
            await _alert_sources(deps, status.file, recorded, round_, node_id)
        except StoreError as error:
            deps.logger.error(
                "sources file=%s store failure (%s): file skipped, continues",
                status.file.native_id,
                error,
            )


async def run_download_cycle(deps: DownloadDeps, node_id: str) -> None:
    """ONE iteration of the download loop (spec §5). Never raises: tolerates/absorbs.

    Two distinct error DOCTRINES (item I2 - anti-starvation):

    - An unavailable client (``ClientUnreachableError`` from step 0, ``_start_unlisted`` or the
      sources step; on the two reads, also a refused read, ``DownloadRejectedError``) = dead
      client → ABORT the iteration ("a dead client makes everything fail"). We skip the rest;
      the next iteration retries.
    - ``StoreError`` (persistence failure, NO client I/O) → ISOLATED PER STEP: a repo
      failure in one step must NOT starve the others. Each step that can raise
      ``StoreError`` is wrapped separately (log + ``continue`` to the next step), and the
      sources step per download. ``_start_unlisted`` re-reads ``read_tracked_states`` FRESHLY, so
      it runs even if an upstream step partially failed. "NEVER abandon a stalled download": the
      1→2→3→4 order is preserved, each step is best-effort, and step 5, the sources, only
      observes, so it comes last (stage 4, D8).

    The repos are sync → cancellation (shutdown) lands at the network ``await``, never mid-write.

    DECISION (audit 2026-06-23 / observability#5): a ``ClientUnreachableError`` here does NOT
    emit ``ClientUnreachable`` (unlike the search tasks). The E-D5 taxonomy files this
    event under SEARCH only; the download loop is single-client and the label
    ``client=...`` would be meaningless (counter shared with the search workers). The
    unavailability is handled by the next cycle's retry + the warning log. Intentional
    asymmetry.
    """
    # Step 0 - SNAPSHOT: client I/O → unreachable or refused = dead daemon = ABORT.
    try:
        listed_statuses = await deps.download_client.downloads()
    except _UNAVAILABLE as error:
        deps.logger.warning("download daemon unreachable (%s): iteration skipped, retry", error)
        return
    listed_files = frozenset(status.file for status in listed_statuses)
    # Clamped at 0: a nascent download (total not known yet) must not invent free space.
    outstanding_bytes = sum(
        max(status.size_bytes - status.bytes_done, 0) for status in listed_statuses
    )
    # Step 1 - RECONCILE: NO client I/O left (the list came from step 0) → only StoreError.
    # Every step shares that ONE snapshot: a second read could only contradict the first.
    try:
        states = deps.tracked_download_reader.read_tracked_states()
        await _reconcile_states(deps, states, listed_statuses)
    except StoreError as error:
        deps.logger.error(
            "download reconciliation store failure (%s): step skipped, continues", error
        )
    # Step 2 - COMPLETIONS: we RE-READ ``read_tracked_states`` FRESHLY (logic-download#2). Without
    # it, a failure in step 1 left ``states`` frozen/empty → every completed file → ``states.get is
    # None`` → ignored → NO completion recorded the entire cycle. The re-read is also better
    # aligned than ``states={}`` with the nominal case (fresh states), at the cost of one extra
    # repo call (idempotent). A failure of the re-read itself is caught downstream.
    # Steps 2 & 3 - NO client I/O → only StoreError possible, ISOLATED per step (I2):
    # a store failure in one must NOT prevent the other from running.
    try:
        fresh_states = deps.tracked_download_reader.read_tracked_states()
        await _handle_completions(deps, fresh_states, listed_statuses, node_id)
    except StoreError as error:
        deps.logger.error("download completions store failure (%s): step skipped, continues", error)
    # Step 2b - PRESENCE + LOSS: ``latest_seen_at`` is for the next start; loss is measured here.
    try:
        deps.tracked_download_writer.set_seen(listed_statuses, deps.wall_clock.now())
        _fail_lost(deps, listed_files)
    except StoreError as error:
        deps.logger.error("download presence store failure (%s): step skipped, continues", error)
    try:
        await _queue_new_candidates(deps, outstanding_bytes, node_id)
    except StoreError as error:
        deps.logger.error("download candidates store failure (%s): step skipped, continues", error)
    except OSError as error:
        # A missing or unreadable output mount: refuse to admit anything rather than take down
        # the crawler, which also catalogues. Conservative, loud, and retried next cycle.
        deps.logger.error("output directory unmeasurable (%s): no candidate admitted, retry", error)
    # Step 4 - START: client I/O → ClientUnreachableError = dead daemon = ABORT. Re-reads
    # ``read_tracked_states`` FRESHLY, so it runs even if step 3 partially failed.
    try:
        await _start_unlisted(deps, listed_files)
    except ClientUnreachableError as error:
        deps.logger.warning("download daemon unreachable (%s): iteration skipped, retry", error)
        return
    except StoreError as error:
        deps.logger.error("download start store failure (%s): step skipped, retry", error)
    # Step 5 - SOURCES: last, since it only observes; its failure must not skip a start (D8).
    try:
        await _record_sources(deps, listed_statuses, node_id)
    except _UNAVAILABLE as error:
        deps.logger.warning("download daemon unreachable (%s): sources skipped, retry", error)
    except StoreError as error:
        deps.logger.error("download sources store failure (%s): step skipped, retry", error)


async def _sleep_or_wake(deps: DownloadLoopDeps) -> None:
    """Waits ``poll_interval`` OR the ``download`` wake, whichever comes FIRST (spec §5).

    ``asyncio.wait(FIRST_COMPLETED)`` then cancel the loser: a download decision's wake resumes the
    loop immediately; otherwise the fallback poll wakes it at the cadence.
    Shutdown cancellation lands HERE (an ``await``), never mid DB write (sync).
    """
    poll_interval = timedelta(seconds=deps.poll_interval_seconds)
    sleep_task = asyncio.ensure_future(deps.monotonic_clock.sleep(poll_interval))
    wake_task = asyncio.ensure_future(deps.waker.wait(DOWNLOAD_WAKE_SUBJECT))
    try:
        await asyncio.wait({sleep_task, wake_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (sleep_task, wake_task):
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task


async def download_loop(deps: DownloadLoopDeps, node_id: str) -> None:
    """Repeats ``run_download_cycle`` then waits (poll/wake) until shutdown (DECISION D12).

    Launched by ``CrawlerLifecycle`` through ``supervise_loops``; cancellation (shutdown) lands
    at the next ``await`` (a poll or the sleep/wake wait), never mid DB write.
    """
    while not deps.shutdown.is_set():
        await run_download_cycle(deps, node_id)
        if deps.shutdown.is_set():
            break
        await _sleep_or_wake(deps)
