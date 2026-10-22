"""CheckStaleClaims: the claims whose advisory the scanner no longer finds, located at the VEX."""

from pathlib import PurePath

from tests.fakes.adapters.driven.fake_sarif_writer import FakeSarifWriter, WrittenSarif
from tests.fakes.adapters.driven.fake_vex_reader import FakeVexReader
from tests.fakes.adapters.driven.fake_vulnerability_scanner import FakeVulnerabilityScanner
from vex_checks.application.use_cases.check_stale_claims import CheckStaleClaims
from vex_checks.domain.violations import Violation

REPO_ROOT = PurePath("/repo")
VEX_PATH = REPO_ROOT / "security" / "crawler.vex.openvex.json"
SBOM_PATH = PurePath("/tmp/sbom.syft.json")
CLAIMS = {"CVE-A": "vulnerable_code_not_present", "CVE-B": "vulnerable_code_not_present"}

CVE_B_STALE = Violation("CVE-B", "no longer reported by Grype", "security/crawler.vex.openvex.json")


def _checker(
    vulnerability_scanner: FakeVulnerabilityScanner,
    sarif_writer: FakeSarifWriter | None = None,
) -> CheckStaleClaims:
    return CheckStaleClaims(
        repo_root=REPO_ROOT,
        vulnerability_scanner=vulnerability_scanner,
        vex_reader=FakeVexReader(CLAIMS),
        sarif_writer=sarif_writer if sarif_writer is not None else FakeSarifWriter(),
    )


def test_a_claim_the_scanner_no_longer_finds_is_a_problem_located_at_the_vex() -> None:
    checker = _checker(FakeVulnerabilityScanner({"CVE-A"}))

    report = checker.check_stale_claims(SBOM_PATH, VEX_PATH, None)

    assert report.problems == (CVE_B_STALE,)


def test_no_claim_is_stale_while_the_scanner_finds_every_advisory() -> None:
    checker = _checker(FakeVulnerabilityScanner({"CVE-A", "CVE-B", "CVE-UNCLAIMED"}))

    report = checker.check_stale_claims(SBOM_PATH, VEX_PATH, None)

    assert report.problems == ()


def test_a_vex_outside_the_repository_is_located_at_its_path_as_given() -> None:
    checker = _checker(FakeVulnerabilityScanner({"CVE-A"}))

    report = checker.check_stale_claims(SBOM_PATH, PurePath("/tmp/vex.openvex.json"), None)

    assert [problem.location for problem in report.problems] == ["/tmp/vex.openvex.json"]


def test_the_scanner_is_given_the_sbom() -> None:
    vulnerability_scanner = FakeVulnerabilityScanner({"CVE-A", "CVE-B"})

    _checker(vulnerability_scanner).check_stale_claims(SBOM_PATH, VEX_PATH, None)

    assert vulnerability_scanner.scanned_sbom_paths == [SBOM_PATH]


def test_asked_for_sarif_the_problems_are_written_under_the_stale_claims_rule() -> None:
    sarif_writer = FakeSarifWriter()
    checker = _checker(FakeVulnerabilityScanner({"CVE-A"}), sarif_writer)

    report = checker.check_stale_claims(SBOM_PATH, VEX_PATH, PurePath("/tmp/out.sarif"))

    assert report.problems == (CVE_B_STALE,)
    assert sarif_writer.written_sarifs == [
        WrittenSarif(
            PurePath("/tmp/out.sarif"),
            "stale-vex-entry",
            (CVE_B_STALE,),
            "security/crawler.vex.openvex.json",
        )
    ]


def test_asked_for_sarif_with_no_stale_claim_an_empty_report_is_written() -> None:
    sarif_writer = FakeSarifWriter()
    checker = _checker(FakeVulnerabilityScanner({"CVE-A", "CVE-B"}), sarif_writer)

    checker.check_stale_claims(SBOM_PATH, VEX_PATH, PurePath("/tmp/out.sarif"))

    assert [written.violations for written in sarif_writer.written_sarifs] == [()]


def test_not_asked_for_sarif_nothing_is_written() -> None:
    sarif_writer = FakeSarifWriter()
    checker = _checker(FakeVulnerabilityScanner({"CVE-A"}), sarif_writer)

    checker.check_stale_claims(SBOM_PATH, VEX_PATH, None)

    assert sarif_writer.written_sarifs == []
