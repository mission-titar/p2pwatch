"""CheckImageClaims: the image premises the VEX claims, against the SBOM, located at the VEX."""

from collections.abc import Mapping
from pathlib import PurePath

from tests.fakes.adapters.driven.fake_sarif_writer import FakeSarifWriter, WrittenSarif
from tests.fakes.adapters.driven.fake_sbom_reader import FakeSbomReader
from tests.fakes.adapters.driven.fake_vex_reader import FakeVexReader
from vex_checks.application.use_cases.check_image_claims import CheckImageClaims
from vex_checks.domain.descriptors import (
    DeclaredMinVersion,
    DpkgMinVersion,
    DpkgPackageAbsent,
    ImagePremise,
)
from vex_checks.domain.registry import PREMISES
from vex_checks.domain.sbom_components import DeclaredComponent, DpkgPackage
from vex_checks.domain.violations import Violation

REPO_ROOT = PurePath("/repo")
VEX_PATH = REPO_ROOT / "security" / "crawler.vex.openvex.json"
SBOM_PATH = PurePath("/tmp/sbom.syft.json")

NGHTTP2_PRESENT = Violation(
    "CVE-IMAGE", "dpkg package 'nghttp2' is present", "security/crawler.vex.openvex.json"
)


def _checker(
    *,
    premises: Mapping[str, ImagePremise],
    claims: dict[str, str],
    sbom_reader: FakeSbomReader,
    sarif_writer: FakeSarifWriter | None = None,
) -> CheckImageClaims:
    return CheckImageClaims(
        premises=premises,
        repo_root=REPO_ROOT,
        vex_reader=FakeVexReader(claims),
        sbom_reader=sbom_reader,
        sarif_writer=sarif_writer if sarif_writer is not None else FakeSarifWriter(),
    )


def test_a_claimed_image_premise_the_sbom_falsifies_is_a_problem_located_at_the_vex() -> None:
    checker = _checker(
        premises={"CVE-IMAGE": DpkgPackageAbsent("nghttp2")},
        claims={"CVE-IMAGE": "vulnerable_code_not_present"},
        sbom_reader=FakeSbomReader(dpkg_packages=[DpkgPackage("nghttp2", "1.64.0-1")]),
    )

    report = checker.check_image_claims(SBOM_PATH, VEX_PATH, None)

    assert report.problems == (NGHTTP2_PRESENT,)


def test_an_image_premise_the_vex_does_not_claim_is_not_evaluated() -> None:
    checker = _checker(
        premises={"CVE-UNCLAIMED": DpkgMinVersion("curl", "99.0")},
        claims={"CVE-SOURCE": "vulnerable_code_not_in_execute_path"},
        sbom_reader=FakeSbomReader(dpkg_packages=[DpkgPackage("curl", "8.14.1-2")]),
    )

    report = checker.check_image_claims(SBOM_PATH, VEX_PATH, None)

    assert report.problems == ()


def test_a_vex_outside_the_repository_is_located_at_its_path_as_given() -> None:
    vex_path = PurePath("/tmp/vex.openvex.json")
    checker = _checker(
        premises={"CVE-IMAGE": DpkgPackageAbsent("nghttp2")},
        claims={"CVE-IMAGE": "vulnerable_code_not_present"},
        sbom_reader=FakeSbomReader(dpkg_packages=[DpkgPackage("nghttp2", "1.64.0-1")]),
    )

    report = checker.check_image_claims(SBOM_PATH, vex_path, None)

    assert [problem.location for problem in report.problems] == ["/tmp/vex.openvex.json"]


def test_the_registry_fails_the_amule_claims_on_an_amule_older_than_the_fix() -> None:
    checker = _checker(
        premises=PREMISES,
        claims={
            "CVE-2006-2691": "vulnerable_code_not_present",
            "CVE-2006-2692": "vulnerable_code_not_present",
        },
        sbom_reader=FakeSbomReader(declared_components=[DeclaredComponent("amule", "2.1.1")]),
    )

    report = checker.check_image_claims(SBOM_PATH, VEX_PATH, None)

    assert [problem.message for problem in report.problems] == [
        "declared amule 2.1.1 is below 2.1.2",
        "declared amule 2.1.1 is below 2.1.2",
    ]


def test_asked_for_sarif_the_problems_are_written_under_the_image_claims_rule() -> None:
    sarif_writer = FakeSarifWriter()
    checker = _checker(
        premises={"CVE-IMAGE": DpkgPackageAbsent("nghttp2")},
        claims={"CVE-IMAGE": "vulnerable_code_not_present"},
        sbom_reader=FakeSbomReader(dpkg_packages=[DpkgPackage("nghttp2", "1.64.0-1")]),
        sarif_writer=sarif_writer,
    )

    report = checker.check_image_claims(SBOM_PATH, VEX_PATH, PurePath("/tmp/out.sarif"))

    assert report.problems == (NGHTTP2_PRESENT,)
    assert sarif_writer.written_sarifs == [
        WrittenSarif(
            PurePath("/tmp/out.sarif"),
            "unsatisfied-image-claim",
            (NGHTTP2_PRESENT,),
            "security/crawler.vex.openvex.json",
        )
    ]


def test_not_asked_for_sarif_nothing_is_written() -> None:
    sarif_writer = FakeSarifWriter()
    checker = _checker(
        premises={"CVE-2006-2691": DeclaredMinVersion("amule", "2.1.2")},
        claims={"CVE-2006-2691": "vulnerable_code_not_present"},
        sbom_reader=FakeSbomReader(declared_components=[DeclaredComponent("amule", "2.1.1")]),
        sarif_writer=sarif_writer,
    )

    checker.check_image_claims(SBOM_PATH, VEX_PATH, None)

    assert sarif_writer.written_sarifs == []
