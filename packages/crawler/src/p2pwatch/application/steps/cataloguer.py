"""The cataloguer, the per-observation pipeline: record → delegate to the file judge (spec §4).

APPLICATION ring (orchestration spec §4): writes through the ``ObservationWriter`` and hands the
file to ``FileJudge``, doing no I/O itself. For EACH observation (spec §4):

1. ``record_observation`` ALWAYS (periodic re-observation is the goal, spec §3/§6).
2. ``FileJudge.rejudge`` (``file_judge.py``) does the rest: evaluate via the pure
   engine, compare against the latest known verdict, and append (or retract) + dispatch + wake
   only on a genuine change. Identical verdict, or a file that was never matched and still
   isn't → no write, no dispatch, no wake.

The stores are SYNCHRONOUS, called DIRECTLY (spec §3: sub-ms, no ``to_thread`` in the
MVP; accepted consequence: DB writes are de facto serialized on the event loop).
A ``StoreError`` (a PORT's error type, never an adapter's) on ONE observation is
LOGGED and ABSORBED here: ``catalog`` returns ``0`` and the cycle continues (spec §7) - a
single corrupt/failed obs does not bring down the whole sweep, but the failure stays
VISIBLE (``error``-level log, so a persistent failure gets noticed).
"""

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.observation_writer import ObservationWriter
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.observability.events import ObservationRecorded
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.store_error import StoreError


class Cataloguer:
    """Records each reported file as an observation, then has the file judged again."""

    def __init__(
        self,
        *,
        observation_writer: ObservationWriter,
        file_judge: FileJudge,
        observability_dispatcher: ObservabilityDispatcher,
        wall_clock: WallClock,
        logger: Logger,
    ) -> None:
        self._observation_writer = observation_writer
        self._file_judge = file_judge
        self._observability_dispatcher = observability_dispatcher
        self._wall_clock = wall_clock
        self._logger = logger

    async def catalog(
        self, reported_file: ReportedFile, client_name: str, channel: str, node_id: str
    ) -> int:
        """Process ONE observation (spec §7). Returns the number of rows written (0..N).

        Dispatches ``ObservationRecorded`` (always), one ``DecisionsRecorded`` when a row was
        written. A ``StoreError`` is absorbed (log + ``0``), the cycle continues (spec §7)."""
        try:
            self._observation_writer.record_observation(
                FileObservation(reported_file, self._wall_clock.now(), node_id)
            )
            await self._observability_dispatcher.dispatch(ObservationRecorded(client_name, channel))
            return await self._file_judge.rejudge(
                reported_file.file, reported_file.to_candidate(), node_id
            )
        except StoreError as error:
            self._logger.error(
                "persistence failed on file=%s:%s (%s): observation skipped, cycle continues",
                reported_file.file.network,
                reported_file.file.native_id,
                error,
            )
            return 0
