"""Checks a VEX's claims against a vulnerability scan of a built image's SBOM."""

from pathlib import PurePath

from vex_checks.application.ports.driven.code_scanning_reporter import CodeScanningReporter
from vex_checks.application.ports.driven.vex_reader import VexReader
from vex_checks.application.ports.driven.vulnerability_scanner import VulnerabilityScanner
from vex_checks.application.ports.driving.applied_claims_checker import (
    AppliedClaimsChecker,
    AppliedClaimsReport,
)
from vex_checks.domain.claim_problem import ClaimProblem
from vex_checks.domain.vex_location import locate_vex

_RULE_ID = "stale-vex-entry"


class CheckAppliedClaims(AppliedClaimsChecker):
    """A claim outlives its subject once the scan stops reporting its advisory: it should be
    pruned. Names a VEX inside ``repository_root`` relative to it."""

    def __init__(
        self,
        *,
        repository_root: PurePath,
        vulnerability_scanner: VulnerabilityScanner,
        vex_reader: VexReader,
        code_scanning_reporter: CodeScanningReporter,
    ) -> None:
        self._repository_root = repository_root
        self._vulnerability_scanner = vulnerability_scanner
        self._vex_reader = vex_reader
        self._code_scanning_reporter = code_scanning_reporter

    def check_applied_claims(
        self, sbom_path: PurePath, vex_path: PurePath, sarif_path: PurePath | None
    ) -> AppliedClaimsReport:
        advisory_ids = self._vulnerability_scanner.scan_sbom(sbom_path)
        vex_location = locate_vex(vex_path, self._repository_root)
        problems = tuple(
            ClaimProblem(advisory_id, "no longer reported by Grype")
            for advisory_id in self._vex_reader.read_claims(vex_path)
            if advisory_id not in advisory_ids
        )
        if sarif_path is not None:
            self._code_scanning_reporter.report_claim_problems(
                sarif_path, _RULE_ID, problems, vex_location
            )
        return AppliedClaimsReport(problems=problems, vex_location=vex_location)
