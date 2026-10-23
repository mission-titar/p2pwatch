"""Queues the download decisions the node does not track yet."""

from collections.abc import Sequence

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.models import TargetSegment
from p2pwatch.application.steps.download_deps import DownloadDeps
from p2pwatch.domain.download.policy import DownloadVerdict, decide_download
from p2pwatch.domain.observability.events import DiskSpaceLow, DownloadQueued, FreeSpaceSampled


def _target_status(targets: Sequence[TargetSegment], target_id: str) -> str:
    """Target status (lookup ``target_id → status``); ``complete`` by default if the target
    has vanished from the config (conservative: do not download for an unknown target)."""
    for target in targets:
        if target.target_id == target_id:
            return target.status
    return "complete"


async def queue_new_candidates(deps: DownloadDeps, outstanding_bytes: int, node_id: str) -> None:
    """Replays tier=download decisions missing from ``downloads`` (step 3, spec §5).

    ``outstanding_bytes`` is what the client still has to transfer, measured from the cycle's
    snapshot; ``free_bytes`` is read once here. Both are MEASURED, never declared.
    """
    free_bytes = deps.free_space_meter.free_bytes()
    await deps.observability_dispatcher.dispatch(FreeSpaceSampled(free_bytes=free_bytes))
    if free_bytes >= deps.min_free_bytes:
        deps.disk_low_edge.leave("disk_low")
    elif deps.disk_low_edge.enter("disk_low"):
        await deps.observability_dispatcher.dispatch(
            DiskSpaceLow(free_bytes=free_bytes, min_free_bytes=deps.min_free_bytes, node_id=node_id)
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
            tier=DecisionTier.DOWNLOAD,
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
        # record_queued ONLY here (sync DB write); start_unlisted sends it (network I/O): the
        # write precedes the network, and a start that raises leaves it 'queued' for next round.
        deps.tracked_download_writer.record_queued(
            candidate.file, candidate.target_id, size_bytes, deps.wall_clock.now()
        )
        deps.loss_deadline_by_file[candidate.file] = deps.monotonic_clock.now() + deps.lost_after
        outstanding_bytes += size_bytes  # the client does not list it yet
        deps.logger.info("candidate file=%s queued for download", candidate.file.native_id)
        await deps.observability_dispatcher.dispatch(DownloadQueued(target_id=candidate.target_id))
