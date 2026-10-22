"""Shared decision helper: evaluate → set-diff → record / retract → wake → emit (spec §7).

APPLICATION layer, PURE orchestration (no ``try/except`` here: a ``RepositoryError`` is a
port contract each CALLER absorbs on its own terms, cf. ``record_observation`` and
``reevaluate_catalog``). Used by BOTH the per-observation pipeline (``record_observations.py``)
and the startup catalogue re-evaluation, so the set-diff + retraction + wake logic is written once.

Set diff keyed by ``(file, target_id)`` (spec §7). The file is judged on EVERY filename the
catalog knows for it (``engine.evaluate_file``, spec amuleapi-migration §8.4), so its filenames
no longer retract each other. A fresh decision is persisted (a download one also wakes the
download loop) only when it differs from the file's LATEST persisted :class:`DecisionRecord`
for THAT target; a target that dropped out of the fresh set is retracted, unless it is already
retracted (no-op). Returns the number of rows written (0..N; a decision OR a retraction each
counts as one). The rows written are emitted once, as one ``DecisionsRecorded`` for the file
(spec researcher-notifications §2).
"""

from dataclasses import replace

from catalog_matching.domain.engine import MatchingEngine, to_record
from catalog_matching.domain.models import FileCandidate
from p2pwatch.application.ports.driven.decision_reader import DecisionReader
from p2pwatch.application.ports.driven.decision_writer import DecisionWriter
from p2pwatch.application.ports.driven.event_emitter import EventEmitter
from p2pwatch.application.ports.driven.observation_reader import ObservationReader
from p2pwatch.application.ports.driven.waker import Waker
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.run_download_cycle import DOWNLOAD_WAKE_SUBJECT
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.observability.events import DecisionChange, DecisionsRecorded
from p2pwatch.domain.retraction import RETRACTED_TIER


async def rejudge_file(
    file: FileKey,
    base_candidate: FileCandidate,
    *,
    observation_reader: ObservationReader,
    decision_writer: DecisionWriter,
    decision_reader: DecisionReader,
    engine: MatchingEngine,
    waker: Waker,
    event_emitter: EventEmitter,
    wall_clock: WallClock,
    node_id: str,
) -> int:
    """Judge the file on all its known filenames for every target, then record what changed
    (``base_candidate`` gives the fields other than the filename).

    Returns the number of rows written (0..N). May propagate ``RepositoryError`` (pure
    orchestration; the caller absorbs it)."""
    filenames = observation_reader.read_known_filenames(file)
    fresh = engine.evaluate_file(
        replace(base_candidate, filename=filename) for filename in filenames
    )
    persisted = decision_reader.read_latest_decisions(file)
    changes: list[DecisionChange] = []

    def change(target_id: str, new_tier: str) -> DecisionChange:
        target = engine.target(target_id)
        previous_record = persisted.get(target_id)
        return DecisionChange(
            target_id,
            "" if target is None else target.title,
            None if previous_record is None else previous_record.tier,
            new_tier,
        )

    fresh_ids: set[str] = set()
    for decision in fresh:
        fresh_ids.add(decision.target_id)
        if persisted.get(decision.target_id) == to_record(decision):
            continue
        decision_writer.record_decision(file, decision, wall_clock.now(), node_id)
        changes.append(change(decision.target_id, decision.tier))
        if decision.tier == "download":
            waker.wake(DOWNLOAD_WAKE_SUBJECT)
    for target_id in sorted(persisted):
        if persisted[target_id].tier == RETRACTED_TIER or target_id in fresh_ids:
            continue
        decision_writer.record_retraction(file, target_id, wall_clock.now(), node_id)
        changes.append(change(target_id, RETRACTED_TIER))
    if changes:
        # No filename left means only retractions were written, which are never notified.
        best = observation_reader.read_best_observation(file)
        if best is None:
            filename, size_bytes = base_candidate.filename, 0
        else:
            filename, size_bytes = best.reported_file.filename, best.reported_file.size_bytes
        await event_emitter.emit(
            DecisionsRecorded(file, filename, size_bytes, tuple(changes)), node_id
        )
    return len(changes)
