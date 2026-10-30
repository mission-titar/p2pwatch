"""Re-judges the whole catalog at the start when the policy changed since the last pass."""

from dataclasses import dataclass

from p2pwatch.application.ports.driven.catalog_scan_reader import CatalogScanReader
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.policy_fingerprint_reader import PolicyFingerprintReader
from p2pwatch.application.ports.driven.policy_fingerprint_writer import PolicyFingerprintWriter
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.store_error import StoreError


@dataclass(kw_only=True, frozen=True)
class ReevaluationSummary:
    """One pass: the files judged (one per catalogued hash) and the rows ``FileJudge`` wrote, a
    retraction counting as one."""

    files_evaluated: int
    rows_written: int


class CatalogReevaluator:
    """Re-judges every catalogued file's latest observation through the shared ``FileJudge``, so
    a re-evaluation writes, wakes and dispatches as the live path does."""

    def __init__(
        self,
        *,
        policy_fingerprint: str,
        policy_fingerprint_reader: PolicyFingerprintReader,
        policy_fingerprint_writer: PolicyFingerprintWriter,
        file_judge: FileJudge,
        catalog_scan_reader: CatalogScanReader,
        progress_every_files: int,
        logger: Logger,
    ) -> None:
        self._policy_fingerprint = policy_fingerprint
        self._policy_fingerprint_reader = policy_fingerprint_reader
        self._policy_fingerprint_writer = policy_fingerprint_writer
        self._file_judge = file_judge
        self._catalog_scan_reader = catalog_scan_reader
        self._progress_every_files = progress_every_files
        self._logger = logger

    async def reevaluate_if_policy_changed(self, node_id: NodeId) -> None:
        """Re-evaluates iff the stored policy fingerprint differs, then stores it; logs either
        outcome."""
        if self._policy_fingerprint_reader.read_policy_fingerprint() == self._policy_fingerprint:
            self._logger.info("policy unchanged: catalogue re-evaluation skipped")
            return
        summary = await self._reevaluate_catalog(node_id)
        # Stored only once the pass ends: a pass that raises is retried at the next start.
        self._policy_fingerprint_writer.set_policy_fingerprint(self._policy_fingerprint)
        self._logger.info(
            "catalogue re-evaluated: %d files, %d rows written",
            summary.files_evaluated,
            summary.rows_written,
        )

    async def _reevaluate_catalog(self, node_id: NodeId) -> ReevaluationSummary:
        """Judges each file in turn; a ``StoreError`` on one is logged and the sweep goes on."""
        total = self._catalog_scan_reader.read_file_count()
        files_evaluated = 0
        rows_written = 0
        for observation in self._catalog_scan_reader.iter_latest_observations():
            files_evaluated += 1
            reported_file = observation.reported_file
            try:
                rows_written += await self._file_judge.rejudge(
                    reported_file.file, base_candidate=reported_file.to_candidate(), node_id=node_id
                )
            except StoreError as error:
                self._logger.error(
                    "persistence failed on file=%s:%s (%s): re-evaluation skipped, sweep continues",
                    reported_file.file.network,
                    reported_file.file.native_id,
                    error,
                )
            if files_evaluated % self._progress_every_files == 0:
                self._logger.info(
                    "catalogue re-evaluation: %d/%d files, %d rows written",
                    files_evaluated,
                    total,
                    rows_written,
                )
        return ReevaluationSummary(files_evaluated=files_evaluated, rows_written=rows_written)
