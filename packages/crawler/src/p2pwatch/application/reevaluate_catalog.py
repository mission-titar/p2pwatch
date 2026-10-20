"""Re-evaluation use-case: re-evaluate the whole catalogue against the current matcher (spec §7).

APPLICATION layer. Iterates every catalogued hash's LATEST observation
(``catalog_scanner.iter_latest_observations()``), rebuilds a :class:`FileCandidate` via
``ReportedFile.to_candidate`` (the single conversion, spec re-evaluation §6), and delegates to
the shared ``rejudge_file`` helper (``decisions.py``, which judges the hash on
all its known filenames) so retraction + notify/download wakes happen identically to the live
per-observation path (spec §4). Only the counting + per-row error absorption are specific
to the re-evaluation.

A per-row ``RepositoryError`` is logged (error level) and absorbed here: one bad file must
not abort the whole sweep (spec §7, same discipline as ``record_observation``).
"""

from dataclasses import dataclass

from catalog_matching.domain.engine import MatchingEngine
from p2pwatch.application.decisions import rejudge_file
from p2pwatch.ports.driven.catalog import (
    CatalogScanner,
    DecisionReader,
    DecisionWriter,
    ObservationReader,
)
from p2pwatch.ports.driven.clock import WallClock
from p2pwatch.ports.driven.logger import Logger
from p2pwatch.ports.driven.repository_errors import RepositoryError
from p2pwatch.ports.driven.telemetry import Telemetry
from p2pwatch.ports.driven.wake_hub import WakeHub

# One INFO progress line per this many files, so a long sweep visibly advances.
_PROGRESS_EVERY = 200


@dataclass(frozen=True)
class ReevaluationSummary:
    """Outcome of one re-evaluation pass (spec §7).

    ``files_evaluated``: rows iterated (one per catalogued hash). ``rows_written``: rows actually
    appended by ``rejudge_file`` (a re-tiered decision OR a retraction -
    no separate retracted count, spec Task 5: "a retraction is just a written row").
    """

    files_evaluated: int
    rows_written: int


async def reevaluate_catalog(
    *,
    observation_reader: ObservationReader,
    decision_writer: DecisionWriter,
    decision_reader: DecisionReader,
    catalog_scanner: CatalogScanner,
    engine: MatchingEngine,
    wake_hub: WakeHub,
    telemetry: Telemetry,
    wall_clock: WallClock,
    logger: Logger,
    node_id: str,
) -> ReevaluationSummary:
    """Re-evaluate every catalogued hash's latest observation against ``engine``.

    Per-item isolation (spec §7): a ``RepositoryError`` on one row is logged and the sweep
    continues with the next row.
    """
    total = catalog_scanner.read_file_count()
    files_evaluated = 0
    rows_written = 0
    for observation in catalog_scanner.iter_latest_observations():
        files_evaluated += 1
        reported_file = observation.reported_file
        try:
            rows_written += await rejudge_file(
                reported_file.file,
                reported_file.to_candidate(),
                observation_reader=observation_reader,
                decision_writer=decision_writer,
                decision_reader=decision_reader,
                engine=engine,
                wake_hub=wake_hub,
                telemetry=telemetry,
                wall_clock=wall_clock,
                node_id=node_id,
            )
        except RepositoryError as error:
            logger.error(
                "persistence failed on file=%s:%s (%s): re-evaluation skipped, sweep continues",
                reported_file.file.network,
                reported_file.file.native_id,
                error,
            )
        if files_evaluated % _PROGRESS_EVERY == 0:
            logger.info(
                "catalogue re-evaluation: %d/%d files, %d rows written",
                files_evaluated,
                total,
                rows_written,
            )
    return ReevaluationSummary(files_evaluated=files_evaluated, rows_written=rows_written)
