"""Per-observation pipeline: record → delegate to the shared decision helper (spec §4).

APPLICATION layer (orchestration spec §4): orchestrates PORTS (sync repos + pure engine
+ async waker), does no I/O itself. For EACH observation (spec §4):

1. ``record_observation`` ALWAYS (periodic re-observation is the goal, spec §3/§6).
2. ``rejudge_file`` (``decisions.py``) does the rest: evaluate via the pure
   engine, compare against the latest known verdict, and append (or retract) + emit + wake
   only on a genuine change. Identical verdict, or a file that was never matched and still
   isn't → no write, no emit, no wake.

The repos are SYNCHRONOUS, called DIRECTLY (spec §3: sub-ms, no ``to_thread`` in the
MVP; accepted consequence: DB writes are de facto serialized on the event loop).
A ``RepositoryError`` (a PORT contract, never an adapter) on ONE observation is
LOGGED and ABSORBED here: the function returns ``0`` and the cycle continues (spec §7) - a
single corrupt/failed obs does not bring down the whole sweep, but the failure stays
VISIBLE (``error``-level log, so a persistent failure gets noticed).
"""

from catalog_matching.domain.engine import MatchingEngine
from p2pwatch.application.ports.driven.decision_reader import DecisionReader
from p2pwatch.application.ports.driven.decision_writer import DecisionWriter
from p2pwatch.application.ports.driven.event_emitter import EventEmitter
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.observation_reader import ObservationReader
from p2pwatch.application.ports.driven.observation_writer import ObservationWriter
from p2pwatch.application.ports.driven.waker import Waker
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.decisions import rejudge_file
from p2pwatch.domain.observability.events import ObservationRecorded
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.repository_errors import RepositoryError


async def record_observation(
    reported_file: ReportedFile,
    *,
    observation_writer: ObservationWriter,
    observation_reader: ObservationReader,
    decision_writer: DecisionWriter,
    decision_reader: DecisionReader,
    engine: MatchingEngine,
    waker: Waker,
    event_emitter: EventEmitter,
    wall_clock: WallClock,
    client_name: str,
    channel: str,
    logger: Logger,
    node_id: str,
) -> int:
    """Process ONE observation (spec §7). Returns the number of rows written (0..N).

    Emits ``ObservationRecorded`` (always) and one ``DecisionsRecorded`` when a row was written.
    A ``RepositoryError`` is absorbed (log + ``0``), the cycle continues (spec §7)."""
    try:
        observation_writer.record_observation(
            FileObservation(reported_file, wall_clock.now()), node_id
        )
        await event_emitter.emit(ObservationRecorded(client_name, channel), node_id)
        return await rejudge_file(
            reported_file.file,
            reported_file.to_candidate(),
            observation_reader=observation_reader,
            decision_writer=decision_writer,
            decision_reader=decision_reader,
            engine=engine,
            waker=waker,
            event_emitter=event_emitter,
            wall_clock=wall_clock,
            node_id=node_id,
        )
    except RepositoryError as error:
        logger.error(
            "persistence failed on file=%s:%s (%s): observation skipped, cycle continues",
            reported_file.file.network,
            reported_file.file.native_id,
            error,
        )
        return 0
