"""Follows the client's list: states, completions, presence, loss."""

from collections.abc import Sequence
from datetime import timedelta
from typing import Literal

from catalog_matching.domain.models import TargetSegment
from p2pwatch.application.ports.driven.decision_reader import DecisionReader
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.observation_reader import ObservationReader
from p2pwatch.application.ports.driven.tracked_download_reader import TrackedDownloadReader
from p2pwatch.application.ports.driven.tracked_download_writer import TrackedDownloadWriter
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.download_file_reads import best_filename, target_titles
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.download.states import DownloadState, FailureReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.observability.events import DownloadCompleted, TargetTitle
from p2pwatch.domain.persisted_wait import remaining_wait
from p2pwatch.domain.store_error import StoreError


class DownloadTracker:
    """Follows the client's list for the downloads the node tracks; owns their loss deadlines."""

    def __init__(
        self,
        *,
        tracked_download_writer: TrackedDownloadWriter,
        tracked_download_reader: TrackedDownloadReader,
        decision_reader: DecisionReader,
        observation_reader: ObservationReader,
        targets: Sequence[TargetSegment],
        lost_after: timedelta,
        wall_clock: WallClock,
        monotonic_clock: MonotonicClock,
        observability_dispatcher: ObservabilityDispatcher,
        logger: Logger,
    ) -> None:
        self._tracked_download_writer = tracked_download_writer
        self._tracked_download_reader = tracked_download_reader
        self._decision_reader = decision_reader
        self._observation_reader = observation_reader
        self._targets = targets
        self._lost_after = lost_after
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._observability_dispatcher = observability_dispatcher
        self._logger = logger
        # Each queued or downloading download's instant from which it counts as lost.
        self._loss_deadline_by_file: dict[FileKey, MonotonicInstant] = {}

    async def track(self, listed_statuses: tuple[DownloadStatus, ...], node_id: str) -> None:
        """Follows ``listed_statuses``: a store failure in one step skips that step only."""
        # Step 1 - RECONCILE: NO client I/O left (the list came from step 0) → only StoreError.
        # Every step shares that ONE snapshot: a second read could only contradict the first.
        try:
            states = self._tracked_download_reader.read_tracked_states()
            self._reconcile_states(states, listed_statuses)
        except StoreError as error:
            self._logger.error(
                "download reconciliation store failure (%s): step skipped, continues", error
            )
        # Step 2 - COMPLETIONS: we RE-READ ``read_tracked_states`` FRESHLY (logic-download#2).
        # Without it, a failure in step 1 left ``states`` frozen/empty → every completed file →
        # ``states.get is None`` → ignored → NO completion recorded the entire cycle. The re-read
        # is also better aligned than ``states={}`` with the nominal case (fresh states), at the
        # cost of one extra store call (idempotent). A failure of the re-read itself is caught
        # downstream.
        try:
            fresh_states = self._tracked_download_reader.read_tracked_states()
            await self._handle_completions(fresh_states, listed_statuses, node_id)
        except StoreError as error:
            self._logger.error(
                "download completions store failure (%s): step skipped, continues", error
            )
        # Step 2b - PRESENCE + LOSS: ``latest_seen_at`` is for the next start; loss is measured
        # here.
        try:
            self._tracked_download_writer.set_seen(listed_statuses, self._wall_clock.now())
            self._fail_lost(frozenset(status.file for status in listed_statuses))
        except StoreError as error:
            self._logger.error(
                "download presence store failure (%s): step skipped, continues", error
            )

    def reset_loss_deadline(self, file: FileKey) -> None:
        """Counts ``lost_after`` from now for ``file``, which the node has just queued."""
        self._loss_deadline_by_file[file] = self._monotonic_clock.now() + self._lost_after

    def _reconcile_states(
        self, states: dict[FileKey, DownloadState], listed_statuses: tuple[DownloadStatus, ...]
    ) -> None:
        """Reconciles ``downloads`` with the client's list: a failure it reports, else DOWNLOADING.

        ``FAILED`` is a wall only while the client reports a failure, so an erroneous download
        does not flap back each round; ``COMPLETED`` is one, so its notification never fires twice.
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
                self._tracked_download_writer.set_state(file, wanted_state, status.failure_reason)
                states[file] = wanted_state

    async def _record_completion(
        self, file: FileKey, states: dict[FileKey, DownloadState], node_id: str
    ) -> None:
        """Marks ``completed`` (stamps completed_at) and notifies (step 2, §5).

        ``completed`` is terminal: the file stays where the client put it, nothing moves it and
        nothing opens it. The caller skips files already ``completed``, so the notification fires
        exactly once per download.
        """
        self._tracked_download_writer.set_completed(file, self._wall_clock.now())
        states[file] = DownloadState.COMPLETED
        titles = target_titles(
            file,
            decision_reader=self._decision_reader,
            tracked_download_reader=self._tracked_download_reader,
            targets=self._targets,
        )
        await self._observability_dispatcher.dispatch(
            DownloadCompleted(
                file,
                best_filename(file, observation_reader=self._observation_reader),
                titles or (TargetTitle("unknown", ""),),
                node_id,
            )
        )
        self._logger.info("file=%s completed", file.native_id)

    async def _handle_completions(
        self,
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
                await self._record_completion(file, states, node_id)
            except StoreError as error:
                self._logger.error(
                    "completion file=%s store failure (%s): file skipped, continues",
                    file.native_id,
                    error,
                )

    def _reconcile_loss_deadlines(
        self, listed_files: frozenset[FileKey], monotonic_now: MonotonicInstant
    ) -> None:
        """Gives each queued or downloading download its loss deadline: ``lost_after`` from now if
        listed, else the one held, else what its ``latest_seen_at`` leaves."""
        deadlines = self._loss_deadline_by_file
        latest_seen_at_by_file = self._tracked_download_reader.read_latest_seen_at_by_file()
        for file in deadlines.keys() - latest_seen_at_by_file.keys():
            del deadlines[file]  # terminal now, or a row the operator deleted for a manual retry
        for file, latest_seen_at in latest_seen_at_by_file.items():
            if file in listed_files:
                deadlines[file] = monotonic_now + self._lost_after
            elif file not in deadlines:
                left = remaining_wait(latest_seen_at, self._lost_after, self._wall_clock.now())
                deadlines[file] = monotonic_now + left

    def _fail_lost(self, listed_files: frozenset[FileKey]) -> None:
        """Fails each download the client has not listed for ``lost_after``.

        It bounds a client that accepts ``start()`` without ever listing the download.
        ``is_tracked`` stays state-blind, so a ``failed`` row still blocks automatic re-queuing;
        the manual retry is deleting the row.
        """
        monotonic_now = self._monotonic_clock.now()
        self._reconcile_loss_deadlines(listed_files, monotonic_now)
        deadlines = self._loss_deadline_by_file
        for file in [file for file, deadline in deadlines.items() if deadline <= monotonic_now]:
            self._tracked_download_writer.set_state(file, DownloadState.FAILED, FailureReason.LOST)
            del deadlines[file]
            self._logger.warning(
                "file=%s unseen by the client for %ss: marked failed",
                file.native_id,
                self._lost_after.total_seconds(),
            )
