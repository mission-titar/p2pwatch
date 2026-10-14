"""Re-evaluation use-case: re-evaluate the whole catalogue against the current matcher (spec §7).

APPLICATION layer. Iterates every catalogued hash's LATEST observation
(``catalog.iter_reevaluation_rows()``), rebuilds a :class:`FileCandidate` via
``candidate_from_fields`` (the single conversion, spec re-evaluation §6), and delegates to
the shared ``rejudge_file`` helper (``decisions.py``, which judges the hash on
all its known filenames) so retraction + notify/download wakes happen identically to the live
per-observation path (spec §4). Only the counting + per-row error absorption are specific
to the re-evaluation.

A per-row ``RepositoryError`` is logged (error level) and absorbed here: one bad file must
not abort the whole sweep (spec §7, same discipline as ``record_observation``).
"""

import logging
from dataclasses import dataclass

from catalog_matching.engine import MatchingEngine
from p2pwatch.application.decisions import rejudge_file
from p2pwatch.domain.observation import candidate_from_fields
from p2pwatch.ports.catalog_repository import CatalogRepository
from p2pwatch.ports.clock import WallClock
from p2pwatch.ports.repository_errors import RepositoryError
from p2pwatch.ports.telemetry import Telemetry
from p2pwatch.ports.wake_hub import WakeHub

_logger = logging.getLogger("p2pwatch.application.reevaluate_catalog")

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
    catalog: CatalogRepository,
    engine: MatchingEngine,
    wake_hub: WakeHub,
    telemetry: Telemetry,
    wall_clock: WallClock,
) -> ReevaluationSummary:
    """Re-evaluate every catalogued hash's latest observation against ``engine``.

    Per-item isolation (spec §7): a ``RepositoryError`` on one row is logged and the sweep
    continues with the next row.
    """
    total = catalog.count_files()
    files_evaluated = 0
    rows_written = 0
    for row in catalog.iter_reevaluation_rows():
        files_evaluated += 1
        candidate = candidate_from_fields(
            row.filename, row.size_bytes, row.duration_seconds, row.bitrate_kbps
        )
        try:
            rows_written += await rejudge_file(
                row.file,
                candidate,
                catalog=catalog,
                engine=engine,
                wake_hub=wake_hub,
                telemetry=telemetry,
                wall_clock=wall_clock,
            )
        except RepositoryError as error:
            _logger.error(
                "persistence failed on file=%s:%s (%s): re-evaluation skipped, sweep continues",
                row.file.network,
                row.file.native_id,
                error,
            )
        if files_evaluated % _PROGRESS_EVERY == 0:
            _logger.info(
                "catalogue re-evaluation: %d/%d files, %d rows written",
                files_evaluated,
                total,
                rows_written,
            )
    return ReevaluationSummary(files_evaluated=files_evaluated, rows_written=rows_written)
