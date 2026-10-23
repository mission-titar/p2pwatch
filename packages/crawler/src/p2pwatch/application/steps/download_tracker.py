"""Follows the client's list: states, completions, loss."""

from typing import Literal

from p2pwatch.application.steps.download_deps import DownloadDeps
from p2pwatch.application.steps.download_file_reads import best_filename, target_titles
from p2pwatch.domain.download.states import DownloadState, FailureReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.observability.events import DownloadCompleted, TargetTitle
from p2pwatch.domain.persisted_wait import remaining_wait
from p2pwatch.domain.store_error import StoreError


async def reconcile_states(
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
    await deps.observability_dispatcher.dispatch(
        DownloadCompleted(
            file,
            best_filename(deps, file),
            target_titles(deps, file) or (TargetTitle("unknown", ""),),
            node_id,
        ),
        node_id,
    )
    deps.logger.info("file=%s completed", file.native_id)


async def handle_completions(
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


def fail_lost(deps: DownloadDeps, listed_files: frozenset[FileKey]) -> None:
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
