"""The file judge: evaluate → record / retract what changed → wake → dispatch (spec §7).

APPLICATION ring, PURE orchestration (no ``try/except`` here: a ``StoreError`` is a
port's error each CALLER absorbs on its own terms, cf. ``Cataloguer`` and
``CatalogReevaluator``). Used by BOTH the per-observation pipeline (``cataloguer.py``)
and the startup catalogue re-evaluation, so the writes, the wake and the event are written once.

The file is judged on EVERY filename the catalog knows for it (``engine.evaluate_file``, spec
amuleapi-migration §8.4), so its filenames no longer retract each other. The domain's
``records_to_write`` decides the rows (spec §7); a download decision also wakes the download
loop. Returns the number of rows written (0..N; a decision OR a retraction each counts as one).
The rows written are dispatched once, as one ``DecisionsRecorded`` for the file (spec
researcher-notifications §2).
"""

from dataclasses import replace

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord, MatchingEngine, to_record
from catalog_matching.domain.models import FileCandidate
from p2pwatch.application.ports.driven.decision_reader import DecisionReader
from p2pwatch.application.ports.driven.decision_writer import DecisionWriter
from p2pwatch.application.ports.driven.observation_reader import ObservationReader
from p2pwatch.application.ports.driven.waker import Waker
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.file_target_decision import DatedDecision, records_to_write
from p2pwatch.domain.observability.events import DecisionChange, DecisionsRecorded
from p2pwatch.domain.wake_subject import WakeSubject


class FileJudge:
    """Judges a file against the targets and records what changed; built once, shared."""

    def __init__(
        self,
        *,
        observation_reader: ObservationReader,
        decision_writer: DecisionWriter,
        decision_reader: DecisionReader,
        engine: MatchingEngine,
        waker: Waker,
        observability_dispatcher: ObservabilityDispatcher,
        wall_clock: WallClock,
    ) -> None:
        self._observation_reader = observation_reader
        self._decision_writer = decision_writer
        self._decision_reader = decision_reader
        self._engine = engine
        self._waker = waker
        self._observability_dispatcher = observability_dispatcher
        self._wall_clock = wall_clock

    async def rejudge(self, file: FileKey, base_candidate: FileCandidate, node_id: str) -> int:
        """Judge the file on all its known filenames for every target, then record what changed
        (``base_candidate`` gives the fields other than the filename).

        Returns the number of rows written (0..N). May propagate ``StoreError`` (pure
        orchestration; the caller absorbs it)."""
        filenames = self._observation_reader.read_known_filenames(file)
        fresh = self._engine.evaluate_file(
            replace(base_candidate, filename=filename) for filename in filenames
        )
        persisted = self._decision_reader.read_latest_decisions(file)
        changes: list[DecisionChange] = []
        for new_decision in records_to_write(
            [to_record(decision) for decision in fresh], persisted
        ):
            target_id = new_decision.target_id
            self._decision_writer.record_decision(
                DatedDecision(file, new_decision, self._wall_clock.now(), node_id)
            )
            if (
                isinstance(new_decision, DecisionRecord)
                and new_decision.tier is DecisionTier.DOWNLOAD
            ):
                self._waker.wake(WakeSubject.DOWNLOAD)
            target = self._engine.target(target_id)
            changes.append(
                DecisionChange(
                    target_id,
                    "" if target is None else target.title,
                    persisted.get(target_id),
                    new_decision,
                )
            )
        if changes:
            # No filename left means only retractions were written, which are never notified.
            best = self._observation_reader.read_best_observation(file)
            if best is None:
                filename, size_bytes = base_candidate.filename, 0
            else:
                filename, size_bytes = best.reported_file.filename, best.reported_file.size_bytes
            await self._observability_dispatcher.dispatch(
                DecisionsRecorded(file, filename, size_bytes, tuple(changes), node_id)
            )
        return len(changes)
