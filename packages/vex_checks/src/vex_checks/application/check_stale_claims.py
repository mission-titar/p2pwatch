"""Checks a VEX's claims against a vulnerability scan of a built image's SBOM."""

from pathlib import PurePath

from vex_checks.domain.vex_location import locate_vex
from vex_checks.domain.violations import Violation
from vex_checks.ports.driven.sarif_writer import SarifWriter
from vex_checks.ports.driven.vex_reader import VexReader
from vex_checks.ports.driven.vulnerability_scanner import VulnerabilityScanner
from vex_checks.ports.driving.stale_claims_checker import StaleClaimsChecker, StaleClaimsReport

_RULE_ID = "stale-vex-entry"


class CheckStaleClaims(StaleClaimsChecker):
    """A claim outlives its subject once the scan stops reporting its advisory: it should be
    pruned. Names a VEX inside ``repo_root`` relative to it."""

    def __init__(
        self,
        *,
        repo_root: PurePath,
        vulnerability_scanner: VulnerabilityScanner,
        vex_reader: VexReader,
        sarif_writer: SarifWriter,
    ) -> None:
        self._repo_root = repo_root
        self._vulnerability_scanner = vulnerability_scanner
        self._vex_reader = vex_reader
        self._sarif_writer = sarif_writer

    def check_stale_claims(
        self, sbom_path: PurePath, vex_path: PurePath, sarif_path: PurePath | None
    ) -> StaleClaimsReport:
        advisory_ids = self._vulnerability_scanner.scan_sbom(sbom_path)
        vex_location = locate_vex(vex_path, self._repo_root)
        problems = tuple(
            Violation(advisory_id, "no longer reported by Grype", vex_location)
            for advisory_id in self._vex_reader.read_claims(vex_path)
            if advisory_id not in advisory_ids
        )
        if sarif_path is not None:
            self._sarif_writer.write_violations(sarif_path, _RULE_ID, problems, vex_location)
        return StaleClaimsReport(problems=problems)
