"""CheckAppliedClaims: the claims whose advisory the scanner no longer finds, located at the VEX."""

from pathlib import PurePath

from tests.fakes.adapters.driven.fake_code_scanning_reporter import (
    FakeCodeScanningReporter,
    WrittenSarif,
)
from tests.fakes.adapters.driven.fake_vex_reader import FakeVexReader
from tests.fakes.adapters.driven.fake_vulnerability_scanner import FakeVulnerabilityScanner
from vex_checks.application.ports.driving.applied_claims_checker import AppliedClaimsReport
from vex_checks.application.use_cases.check_applied_claims import CheckAppliedClaims
from vex_checks.domain.claim_problem import ClaimProblem

REPOSITORY_ROOT = PurePath("/repo")
VEX_PATH = REPOSITORY_ROOT / "security" / "crawler.vex.openvex.json"
SBOM_PATH = PurePath("/tmp/sbom.syft.json")
CLAIMS = {"CVE-A": "vulnerable_code_not_present", "CVE-B": "vulnerable_code_not_present"}

VEX_LOCATION = "security/crawler.vex.openvex.json"

CVE_B_STALE = ClaimProblem("CVE-B", "no longer reported by Grype")


def _checker(
    vulnerability_scanner: FakeVulnerabilityScanner,
    code_scanning_reporter: FakeCodeScanningReporter | None = None,
) -> CheckAppliedClaims:
    return CheckAppliedClaims(
        repository_root=REPOSITORY_ROOT,
        vulnerability_scanner=vulnerability_scanner,
        vex_reader=FakeVexReader(CLAIMS),
        code_scanning_reporter=code_scanning_reporter
        if code_scanning_reporter is not None
        else FakeCodeScanningReporter(),
    )


def test_a_claim_the_scanner_no_longer_finds_is_a_problem_located_at_the_vex() -> None:
    checker = _checker(FakeVulnerabilityScanner({"CVE-A"}))

    report = checker.check_applied_claims(SBOM_PATH, VEX_PATH, None)

    assert report == AppliedClaimsReport(problems=(CVE_B_STALE,), vex_location=VEX_LOCATION)


def test_no_claim_is_stale_while_the_scanner_finds_every_advisory() -> None:
    checker = _checker(FakeVulnerabilityScanner({"CVE-A", "CVE-B", "CVE-UNCLAIMED"}))

    report = checker.check_applied_claims(SBOM_PATH, VEX_PATH, None)

    assert report.problems == ()


def test_a_vex_outside_the_repository_is_located_at_its_path_as_given() -> None:
    checker = _checker(FakeVulnerabilityScanner({"CVE-A"}))

    report = checker.check_applied_claims(SBOM_PATH, PurePath("/tmp/vex.openvex.json"), None)

    assert report.vex_location == "/tmp/vex.openvex.json"


def test_the_scanner_is_given_the_sbom() -> None:
    vulnerability_scanner = FakeVulnerabilityScanner({"CVE-A", "CVE-B"})

    _checker(vulnerability_scanner).check_applied_claims(SBOM_PATH, VEX_PATH, None)

    assert vulnerability_scanner.scanned_sbom_paths == [SBOM_PATH]


def test_asked_for_sarif_the_problems_are_written_under_the_stale_vex_entry_rule() -> None:
    code_scanning_reporter = FakeCodeScanningReporter()
    checker = _checker(FakeVulnerabilityScanner({"CVE-A"}), code_scanning_reporter)

    report = checker.check_applied_claims(SBOM_PATH, VEX_PATH, PurePath("/tmp/out.sarif"))

    assert report == AppliedClaimsReport(problems=(CVE_B_STALE,), vex_location=VEX_LOCATION)
    assert code_scanning_reporter.written_sarifs == [
        WrittenSarif(PurePath("/tmp/out.sarif"), "stale-vex-entry", (CVE_B_STALE,), VEX_LOCATION)
    ]


def test_asked_for_sarif_with_no_stale_claim_an_empty_report_is_written() -> None:
    code_scanning_reporter = FakeCodeScanningReporter()
    checker = _checker(FakeVulnerabilityScanner({"CVE-A", "CVE-B"}), code_scanning_reporter)

    checker.check_applied_claims(SBOM_PATH, VEX_PATH, PurePath("/tmp/out.sarif"))

    assert [written.claim_problems for written in code_scanning_reporter.written_sarifs] == [()]


def test_not_asked_for_sarif_nothing_is_written() -> None:
    code_scanning_reporter = FakeCodeScanningReporter()
    checker = _checker(FakeVulnerabilityScanner({"CVE-A"}), code_scanning_reporter)

    checker.check_applied_claims(SBOM_PATH, VEX_PATH, None)

    assert code_scanning_reporter.written_sarifs == []
