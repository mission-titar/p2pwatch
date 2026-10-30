"""Queues the download decisions the node does not track yet."""

from collections.abc import Sequence

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.identifiers import TargetId
from catalog_matching.domain.models import TargetSegment
from p2pwatch.application.ports.driven.decision_reader import DecisionReader
from p2pwatch.application.ports.driven.free_space_meter import FreeSpaceMeter
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.observation_reader import ObservationReader
from p2pwatch.application.ports.driven.tracked_download_reader import TrackedDownloadReader
from p2pwatch.application.ports.driven.tracked_download_writer import TrackedDownloadWriter
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.download_tracker import DownloadTracker
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.download.policy import DownloadVerdict, decide_download
from p2pwatch.domain.edge_state import EdgeState
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.events import DiskSpaceLow, DownloadQueued, FreeSpaceSampled


def _target_status(targets: Sequence[TargetSegment], *, target_id: TargetId) -> str:
    """Target status (lookup ``target_id → status``); ``complete`` by default if the target
    has vanished from the config (conservative: do not download for an unknown target)."""
    for target in targets:
        if target.target_id == target_id:
            return target.status
    return "complete"


class DownloadDecider:
    """Queues each download decision the disk floor admits; owns the disk-low edge."""

    def __init__(
        self,
        *,
        free_space_meter: FreeSpaceMeter,
        min_free_bytes: int,
        decision_reader: DecisionReader,
        observation_reader: ObservationReader,
        tracked_download_writer: TrackedDownloadWriter,
        tracked_download_reader: TrackedDownloadReader,
        targets: Sequence[TargetSegment],
        download_tracker: DownloadTracker,
        wall_clock: WallClock,
        observability_dispatcher: ObservabilityDispatcher,
        logger: Logger,
    ) -> None:
        self._free_space_meter = free_space_meter
        self._min_free_bytes = min_free_bytes
        self._decision_reader = decision_reader
        self._observation_reader = observation_reader
        self._tracked_download_writer = tracked_download_writer
        self._tracked_download_reader = tracked_download_reader
        self._targets = targets
        self._download_tracker = download_tracker
        self._wall_clock = wall_clock
        self._observability_dispatcher = observability_dispatcher
        self._logger = logger
        self._disk_low_edge = EdgeState()

    async def queue_new_candidates(self, outstanding_bytes: int, *, node_id: NodeId) -> None:
        """Replays tier=download decisions missing from ``downloads`` (step 3, spec §5).

        ``outstanding_bytes`` is what the client still has to transfer, measured from the cycle's
        snapshot; ``free_bytes`` is read once here. Both are MEASURED, never declared.
        """
        free_bytes = self._free_space_meter.free_bytes()
        await self._observability_dispatcher.dispatch(FreeSpaceSampled(free_bytes=free_bytes))
        if free_bytes >= self._min_free_bytes:
            self._disk_low_edge.leave("disk_low")
        elif self._disk_low_edge.enter("disk_low"):
            await self._observability_dispatcher.dispatch(
                DiskSpaceLow(
                    free_bytes=free_bytes, min_free_bytes=self._min_free_bytes, node_id=node_id
                )
            )
        for candidate in self._decision_reader.read_download_candidates():
            if self._tracked_download_reader.is_tracked(candidate.file):
                continue
            observation = self._observation_reader.read_latest_observation(candidate.file)
            if observation is None:
                self._logger.warning(
                    "candidate file=%s without observation: link impossible, skipped",
                    candidate.file.native_id,
                )
                continue
            size_bytes = observation.reported_file.size_bytes
            verdict = decide_download(
                tier=DecisionTier.DOWNLOAD,
                target_status=_target_status(self._targets, target_id=candidate.target_id),
                already_tracked=False,
                free_bytes=free_bytes,
                outstanding_bytes=outstanding_bytes,
                size_bytes=size_bytes,
                min_free_bytes=self._min_free_bytes,
            )
            if verdict is not DownloadVerdict.DOWNLOAD:
                self._logger.info(
                    "candidate file=%s → %s (skipped/deferred)",
                    candidate.file.native_id,
                    verdict.value,
                )
                continue
            # record_queued ONLY here (sync DB write); start_unlisted sends it (network I/O): the
            # write precedes the network, and a start that raises leaves it 'queued' for next round.
            self._tracked_download_writer.record_queued(
                candidate.file,
                target_id=candidate.target_id,
                size_bytes=size_bytes,
                queued_at=self._wall_clock.now(),
            )
            self._download_tracker.reset_loss_deadline(candidate.file)
            outstanding_bytes += size_bytes  # the client does not list it yet
            self._logger.info("candidate file=%s queued for download", candidate.file.native_id)
            await self._observability_dispatcher.dispatch(
                DownloadQueued(target_id=candidate.target_id)
            )
