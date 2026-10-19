"""Per-observation pipeline: record → delegate to the shared decision helper (spec §4).

APPLICATION layer (orchestration spec §4): orchestrates PORTS (sync repos + pure engine
+ async wake hub), does no I/O itself. For EACH observation (spec §4):

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
from p2pwatch.application.decisions import rejudge_file
from p2pwatch.domain.observability.events import ObservationRecorded
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.ports.driven.catalog_repository import CatalogRepository
from p2pwatch.ports.driven.clock import WallClock
from p2pwatch.ports.driven.logger import Logger
from p2pwatch.ports.driven.repository_errors import RepositoryError
from p2pwatch.ports.driven.telemetry import Telemetry
from p2pwatch.ports.driven.wake_hub import WakeHub


async def record_observation(
    reported_file: ReportedFile,
    *,
    catalog: CatalogRepository,
    engine: MatchingEngine,
    wake_hub: WakeHub,
    telemetry: Telemetry,
    wall_clock: WallClock,
    client_name: str,
    channel: str,
    logger: Logger,
) -> int:
    """Process ONE observation (spec §7). Returns the number of rows written (0..N).

    Emits ``ObservationRecorded`` (always) and one ``DecisionsRecorded`` when a row was written.
    A ``RepositoryError`` is absorbed (log + ``0``), the cycle continues (spec §7)."""
    try:
        catalog.record_observation(FileObservation(reported_file, wall_clock.now()))
        await telemetry.emit(ObservationRecorded(client_name, channel))
        return await rejudge_file(
            reported_file.file,
            reported_file.to_candidate(),
            catalog=catalog,
            engine=engine,
            wake_hub=wake_hub,
            telemetry=telemetry,
            wall_clock=wall_clock,
        )
    except RepositoryError as error:
        logger.error(
            "persistence failed on file=%s:%s (%s): observation skipped, cycle continues",
            reported_file.file.network,
            reported_file.file.native_id,
            error,
        )
        return 0
