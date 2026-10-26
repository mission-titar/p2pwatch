"""CheckAppliedClaims: the claims Grype does not report, or does not apply to every match, located
at the VEX."""

import re
from pathlib import PurePath

import pytest

from tests.fakes.adapters.driven.fake_code_scanning_reporter import (
    FakeCodeScanningReporter,
    WrittenSarif,
)
from tests.fakes.adapters.driven.fake_vex_reader import FakeVexReader
from tests.fakes.adapters.driven.fake_vulnerability_scanner import (
    FakeVulnerabilityScanner,
    ScannedSbom,
)
from vex_checks.application.ports.driving.applied_claims_checker import AppliedClaimsReport
from vex_checks.application.use_cases.check_applied_claims import CheckAppliedClaims
from vex_checks.domain.broken_input_error import BrokenInputError
from vex_checks.domain.claim_problem import ClaimProblem
from vex_checks.domain.vulnerability_scan import VulnerabilityScan

REPOSITORY_ROOT = PurePath("/repo")
VEX_PATH = REPOSITORY_ROOT / "security" / "crawler.vex.openvex.json"
SBOM_PATH = PurePath("/tmp/sbom.syft.json")
CLAIMS = {"CVE-A": "vulnerable_code_not_present", "CVE-B": "vulnerable_code_not_present"}

VEX_LOCATION = "security/crawler.vex.openvex.json"

CVE_B_STALE = ClaimProblem("CVE-B", "stale: Grype does not report it")
CVE_B_NOT_APPLIED = ClaimProblem("CVE-B", "not applied: Grype leaves a match unsuppressed")

BOTH_APPLIED = VulnerabilityScan(
    found_advisory_ids=frozenset({"CVE-A", "CVE-B", "CVE-UNCLAIMED"}),
    unsuppressed_advisory_ids=frozenset({"CVE-UNCLAIMED"}),
)
CVE_B_NOT_FOUND = VulnerabilityScan(
    found_advisory_ids=frozenset({"CVE-A"}), unsuppressed_advisory_ids=frozenset()
)


def _checker(
    vulnerability_scanner: FakeVulnerabilityScanner,
    code_scanning_reporter: FakeCodeScanningReporter | None = None,
    vex_reader: FakeVexReader | None = None,
) -> CheckAppliedClaims:
    return CheckAppliedClaims(
        repository_root=REPOSITORY_ROOT,
        vulnerability_scanner=vulnerability_scanner,
        vex_reader=vex_reader if vex_reader is not None else FakeVexReader(CLAIMS),
        code_scanning_reporter=code_scanning_reporter
        if code_scanning_reporter is not None
        else FakeCodeScanningReporter(),
    )


def test_a_claim_grype_does_not_report_is_stale_located_at_the_vex() -> None:
    checker = _checker(FakeVulnerabilityScanner(CVE_B_NOT_FOUND))

    report = checker.check_applied_claims(SBOM_PATH, VEX_PATH, None)

    assert report == AppliedClaimsReport(problems=(CVE_B_STALE,), vex_location=VEX_LOCATION)


def test_a_claim_with_an_unsuppressed_match_is_not_applied_though_others_are_suppressed() -> None:
    # Grype finds CVE-B on two packages and suppresses it on one only.
    scan = VulnerabilityScan(
        found_advisory_ids=frozenset({"CVE-A", "CVE-B"}),
        unsuppressed_advisory_ids=frozenset({"CVE-B"}),
    )
    checker = _checker(FakeVulnerabilityScanner(scan))

    report = checker.check_applied_claims(SBOM_PATH, VEX_PATH, None)

    assert report == AppliedClaimsReport(problems=(CVE_B_NOT_APPLIED,), vex_location=VEX_LOCATION)


def test_no_claim_is_a_problem_while_grype_suppresses_every_match_of_each() -> None:
    checker = _checker(FakeVulnerabilityScanner(BOTH_APPLIED))

    report = checker.check_applied_claims(SBOM_PATH, VEX_PATH, None)

    assert report.problems == ()


def test_a_vex_outside_the_repository_is_located_at_its_path_as_given() -> None:
    checker = _checker(FakeVulnerabilityScanner(BOTH_APPLIED))

    report = checker.check_applied_claims(SBOM_PATH, PurePath("/tmp/vex.openvex.json"), None)

    assert report.vex_location == "/tmp/vex.openvex.json"


def test_the_scanner_is_given_the_sbom_and_the_vex() -> None:
    vulnerability_scanner = FakeVulnerabilityScanner(BOTH_APPLIED)

    _checker(vulnerability_scanner).check_applied_claims(SBOM_PATH, VEX_PATH, None)

    assert vulnerability_scanner.scanned_sboms == [ScannedSbom(SBOM_PATH, VEX_PATH)]


def test_an_unreadable_vex_raises_before_the_scanner_runs() -> None:
    vulnerability_scanner = FakeVulnerabilityScanner(BOTH_APPLIED)
    vex_reader = FakeVexReader(CLAIMS, unreadable_vex_paths=frozenset({VEX_PATH}))
    checker = _checker(vulnerability_scanner, vex_reader=vex_reader)

    with pytest.raises(BrokenInputError, match=f"^{re.escape(str(VEX_PATH))}: no such file$"):
        checker.check_applied_claims(SBOM_PATH, VEX_PATH, None)

    assert vulnerability_scanner.scanned_sboms == []


def test_asked_for_sarif_the_problems_are_written_under_the_unapplied_vex_claim_rule() -> None:
    code_scanning_reporter = FakeCodeScanningReporter()
    checker = _checker(FakeVulnerabilityScanner(CVE_B_NOT_FOUND), code_scanning_reporter)

    report = checker.check_applied_claims(SBOM_PATH, VEX_PATH, PurePath("/tmp/out.sarif"))

    assert report == AppliedClaimsReport(problems=(CVE_B_STALE,), vex_location=VEX_LOCATION)
    assert code_scanning_reporter.written_sarifs == [
        WrittenSarif(
            PurePath("/tmp/out.sarif"), "unapplied-vex-claim", (CVE_B_STALE,), VEX_LOCATION
        )
    ]


def test_asked_for_sarif_with_no_problem_an_empty_report_is_written() -> None:
    code_scanning_reporter = FakeCodeScanningReporter()
    checker = _checker(FakeVulnerabilityScanner(BOTH_APPLIED), code_scanning_reporter)

    checker.check_applied_claims(SBOM_PATH, VEX_PATH, PurePath("/tmp/out.sarif"))

    assert [written.claim_problems for written in code_scanning_reporter.written_sarifs] == [()]


def test_not_asked_for_sarif_nothing_is_written() -> None:
    code_scanning_reporter = FakeCodeScanningReporter()
    checker = _checker(FakeVulnerabilityScanner(CVE_B_NOT_FOUND), code_scanning_reporter)

    checker.check_applied_claims(SBOM_PATH, VEX_PATH, None)

    assert code_scanning_reporter.written_sarifs == []
