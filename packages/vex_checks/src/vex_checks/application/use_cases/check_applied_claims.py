"""Checks that Grype applies a VEX's claims to a vulnerability scan of a built image's SBOM."""

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
from vex_checks.domain.vulnerability_scan import VulnerabilityScan

_RULE_ID = "unapplied-vex-claim"


class CheckAppliedClaims(AppliedClaimsChecker):
    """A claim Grype does not report is stale, one it leaves a match of unsuppressed is not
    applied. Names a VEX inside ``repository_root`` relative to it."""

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
        # Read first, so that the reader names a broken VEX before Grype fails on it.
        claims = self._vex_reader.read_claims(vex_path)
        vulnerability_scan = self._vulnerability_scanner.scan_sbom(sbom_path, vex_path)
        vex_location = locate_vex(vex_path, self._repository_root)
        problems = tuple(
            problem
            for advisory_id in claims
            if (problem := _claim_problem(advisory_id, vulnerability_scan)) is not None
        )
        if sarif_path is not None:
            self._code_scanning_reporter.report_claim_problems(
                sarif_path, _RULE_ID, problems, vex_location
            )
        return AppliedClaimsReport(problems=problems, vex_location=vex_location)


def _claim_problem(advisory_id: str, vulnerability_scan: VulnerabilityScan) -> ClaimProblem | None:
    if advisory_id not in vulnerability_scan.found_advisory_ids:
        return ClaimProblem(advisory_id, "stale: Grype does not report it")
    if advisory_id in vulnerability_scan.unsuppressed_advisory_ids:
        return ClaimProblem(advisory_id, "not applied: Grype leaves a match unsuppressed")
    return None
