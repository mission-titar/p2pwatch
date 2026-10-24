"""Re-evaluation step: re-evaluate the whole catalogue against the current matcher (spec §7).

APPLICATION ring. Iterates every catalogued hash's LATEST observation
(``catalog_scan_reader.iter_latest_observations()``), rebuilds a :class:`FileCandidate` via
``ReportedFile.to_candidate`` (the single conversion, spec re-evaluation §6), and delegates to
the shared ``FileJudge`` (``file_judge.py``, which judges the hash on
all its known filenames) so retraction + notify/download wakes happen identically to the live
per-observation path (spec §4). Only the counting + per-row error absorption are specific
to the re-evaluation.

A per-row ``StoreError`` is logged (error level) and absorbed here: one bad file must
not abort the whole sweep (spec §7, same discipline as ``Cataloguer``).
"""

from dataclasses import dataclass

from p2pwatch.application.ports.driven.catalog_scan_reader import CatalogScanReader
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.domain.store_error import StoreError


@dataclass(frozen=True)
class ReevaluationSummary:
    """Outcome of one re-evaluation pass (spec §7).

    ``files_evaluated``: rows iterated (one per catalogued hash). ``rows_written``: rows actually
    appended by ``FileJudge`` (a re-tiered decision OR a retraction -
    no separate retracted count, spec Task 5: "a retraction is just a written row").
    """

    files_evaluated: int
    rows_written: int


async def reevaluate_catalog(
    *,
    file_judge: FileJudge,
    catalog_scan_reader: CatalogScanReader,
    logger: Logger,
    node_id: str,
    progress_every_files: int,
) -> ReevaluationSummary:
    """Re-evaluate every catalogued hash's latest observation through ``file_judge``.

    Per-item isolation (spec §7): a ``StoreError`` on one row is logged and the sweep
    continues with the next row.
    """
    total = catalog_scan_reader.read_file_count()
    files_evaluated = 0
    rows_written = 0
    for observation in catalog_scan_reader.iter_latest_observations():
        files_evaluated += 1
        reported_file = observation.reported_file
        try:
            rows_written += await file_judge.rejudge(
                reported_file.file, reported_file.to_candidate(), node_id
            )
        except StoreError as error:
            logger.error(
                "persistence failed on file=%s:%s (%s): re-evaluation skipped, sweep continues",
                reported_file.file.network,
                reported_file.file.native_id,
                error,
            )
        if files_evaluated % progress_every_files == 0:
            logger.info(
                "catalogue re-evaluation: %d/%d files, %d rows written",
                files_evaluated,
                total,
                rows_written,
            )
    return ReevaluationSummary(files_evaluated=files_evaluated, rows_written=rows_written)
