"""CheckImageClaims: the image premises the VEX claims, against the SBOM, located at the VEX."""

from collections.abc import Mapping
from pathlib import PurePath

from tests.fakes.adapters.driven.fake_code_scanning_reporter import (
    FakeCodeScanningReporter,
    WrittenSarif,
)
from tests.fakes.adapters.driven.fake_sbom_reader import FakeSbomReader
from tests.fakes.adapters.driven.fake_vex_reader import FakeVexReader
from vex_checks.application.ports.driving.image_claims_checker import ImageClaimsReport
from vex_checks.application.use_cases.check_image_claims import CheckImageClaims
from vex_checks.domain.claim_problem import ClaimProblem
from vex_checks.domain.descriptors import (
    DeclaredMinVersion,
    DpkgMinVersion,
    DpkgPackageAbsent,
    ImagePremise,
)
from vex_checks.domain.registry import PREMISES
from vex_checks.domain.sbom_components import DeclaredComponent, DpkgPackage

REPOSITORY_ROOT = PurePath("/repo")
VEX_PATH = REPOSITORY_ROOT / "security" / "crawler.vex.openvex.json"
SBOM_PATH = PurePath("/tmp/sbom.syft.json")

VEX_LOCATION = "security/crawler.vex.openvex.json"

NGHTTP2_PRESENT = ClaimProblem(advisory_id="CVE-IMAGE", message="dpkg package 'nghttp2' is present")


def _checker(
    *,
    premises: Mapping[str, ImagePremise],
    claims: dict[str, str],
    sbom_reader: FakeSbomReader,
    code_scanning_reporter: FakeCodeScanningReporter | None = None,
) -> CheckImageClaims:
    return CheckImageClaims(
        premises=premises,
        repository_root=REPOSITORY_ROOT,
        vex_reader=FakeVexReader(claims),
        sbom_reader=sbom_reader,
        code_scanning_reporter=code_scanning_reporter
        if code_scanning_reporter is not None
        else FakeCodeScanningReporter(),
    )


def test_a_claimed_image_premise_the_sbom_falsifies_is_a_problem_located_at_the_vex() -> None:
    checker = _checker(
        premises={"CVE-IMAGE": DpkgPackageAbsent(package="nghttp2")},
        claims={"CVE-IMAGE": "vulnerable_code_not_present"},
        sbom_reader=FakeSbomReader(dpkg_packages=[DpkgPackage(name="nghttp2", version="1.64.0-1")]),
    )

    report = checker.check_image_claims(SBOM_PATH, vex_path=VEX_PATH, sarif_path=None)

    assert report == ImageClaimsReport(problems=(NGHTTP2_PRESENT,), vex_location=VEX_LOCATION)


def test_an_image_premise_the_vex_does_not_claim_is_not_evaluated() -> None:
    checker = _checker(
        premises={"CVE-UNCLAIMED": DpkgMinVersion(package="curl", minimum="99.0")},
        claims={"CVE-SOURCE": "vulnerable_code_not_in_execute_path"},
        sbom_reader=FakeSbomReader(dpkg_packages=[DpkgPackage(name="curl", version="8.14.1-2")]),
    )

    report = checker.check_image_claims(SBOM_PATH, vex_path=VEX_PATH, sarif_path=None)

    assert report.problems == ()


def test_a_vex_outside_the_repository_is_located_at_its_path_as_given() -> None:
    vex_path = PurePath("/tmp/vex.openvex.json")
    checker = _checker(
        premises={"CVE-IMAGE": DpkgPackageAbsent(package="nghttp2")},
        claims={"CVE-IMAGE": "vulnerable_code_not_present"},
        sbom_reader=FakeSbomReader(dpkg_packages=[DpkgPackage(name="nghttp2", version="1.64.0-1")]),
    )

    report = checker.check_image_claims(SBOM_PATH, vex_path=vex_path, sarif_path=None)

    assert report.vex_location == "/tmp/vex.openvex.json"


def test_the_registry_fails_the_amule_claims_on_an_amule_older_than_the_fix() -> None:
    checker = _checker(
        premises=PREMISES,
        claims={
            "CVE-2006-2691": "vulnerable_code_not_present",
            "CVE-2006-2692": "vulnerable_code_not_present",
        },
        sbom_reader=FakeSbomReader(
            declared_components=[DeclaredComponent(name="amule", version="2.1.1")]
        ),
    )

    report = checker.check_image_claims(SBOM_PATH, vex_path=VEX_PATH, sarif_path=None)

    assert [problem.message for problem in report.problems] == [
        "declared amule 2.1.1 is below 2.1.2",
        "declared amule 2.1.1 is below 2.1.2",
    ]


def test_asked_for_sarif_the_problems_are_written_under_the_image_claims_rule() -> None:
    code_scanning_reporter = FakeCodeScanningReporter()
    checker = _checker(
        premises={"CVE-IMAGE": DpkgPackageAbsent(package="nghttp2")},
        claims={"CVE-IMAGE": "vulnerable_code_not_present"},
        sbom_reader=FakeSbomReader(dpkg_packages=[DpkgPackage(name="nghttp2", version="1.64.0-1")]),
        code_scanning_reporter=code_scanning_reporter,
    )

    report = checker.check_image_claims(
        SBOM_PATH, vex_path=VEX_PATH, sarif_path=PurePath("/tmp/out.sarif")
    )

    assert report == ImageClaimsReport(problems=(NGHTTP2_PRESENT,), vex_location=VEX_LOCATION)
    assert code_scanning_reporter.written_sarifs == [
        WrittenSarif(
            sarif_path=PurePath("/tmp/out.sarif"),
            rule_id="unsatisfied-image-claim",
            claim_problems=(NGHTTP2_PRESENT,),
            vex_location=VEX_LOCATION,
        )
    ]


def test_not_asked_for_sarif_nothing_is_written() -> None:
    code_scanning_reporter = FakeCodeScanningReporter()
    checker = _checker(
        premises={"CVE-2006-2691": DeclaredMinVersion(component="amule", minimum="2.1.2")},
        claims={"CVE-2006-2691": "vulnerable_code_not_present"},
        sbom_reader=FakeSbomReader(
            declared_components=[DeclaredComponent(name="amule", version="2.1.1")]
        ),
        code_scanning_reporter=code_scanning_reporter,
    )

    checker.check_image_claims(SBOM_PATH, vex_path=VEX_PATH, sarif_path=None)

    assert code_scanning_reporter.written_sarifs == []
