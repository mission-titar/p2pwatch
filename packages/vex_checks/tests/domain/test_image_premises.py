from vex_checks.domain.claim_problem import ClaimProblem
from vex_checks.domain.descriptors import (
    DeclaredMinVersion,
    DpkgMinVersion,
    DpkgPackageAbsent,
    ImagePremise,
)
from vex_checks.domain.image_premises import evaluate_image_premises
from vex_checks.domain.sbom_components import DeclaredComponent, DpkgPackage


def test_package_absent_passes_when_only_sibling_package_present() -> None:
    premises: dict[str, ImagePremise] = {"CVE-2024-0001": DpkgPackageAbsent("libcurl4")}
    packages = [DpkgPackage("libcurl4t64", "8.14.1-2")]
    assert evaluate_image_premises(premises, packages, []) == []


def test_package_absent_fails_when_package_present() -> None:
    premises: dict[str, ImagePremise] = {"CVE-2024-0001": DpkgPackageAbsent("libcurl4")}
    packages = [DpkgPackage("libcurl4", "8.14.1-2")]
    assert evaluate_image_premises(premises, packages, []) == [
        ClaimProblem("CVE-2024-0001", "dpkg package 'libcurl4' is present")
    ]


def test_package_min_version_passes_at_or_above_minimum() -> None:
    premises: dict[str, ImagePremise] = {"CVE-2016-1405": DpkgMinVersion("curl", "8.0")}
    packages = [DpkgPackage("curl", "8.14.1-2")]
    assert evaluate_image_premises(premises, packages, []) == []


def test_package_min_version_fails_below_minimum() -> None:
    premises: dict[str, ImagePremise] = {"CVE-2016-1405": DpkgMinVersion("curl", "8.0")}
    packages = [DpkgPackage("curl", "7.88.1-10+deb12u5")]
    assert evaluate_image_premises(premises, packages, []) == [
        ClaimProblem("CVE-2016-1405", "curl 7.88.1-10+deb12u5 is below 8.0")
    ]


def test_package_min_version_compares_the_upstream_part_of_a_debian_version() -> None:
    # Only the upstream part compares; whole, "1:8.14.1-2" is not a valid version.
    premises: dict[str, ImagePremise] = {"CVE-2016-1405": DpkgMinVersion("curl", "8.14")}
    assert evaluate_image_premises(premises, [DpkgPackage("curl", "1:8.14.1-2")], []) == []


def test_package_min_version_handles_a_version_with_no_revision() -> None:
    # A native Debian package carries no "-revision" at all: the whole string is upstream.
    premises: dict[str, ImagePremise] = {"CVE-2016-1405": DpkgMinVersion("curl", "8.0")}
    assert evaluate_image_premises(premises, [DpkgPackage("curl", "8.14.1")], []) == []


def test_package_min_version_passes_vacuously_when_package_absent() -> None:
    premises: dict[str, ImagePremise] = {"CVE-2016-1405": DpkgMinVersion("curl", "8.0")}
    packages = [DpkgPackage("libcurl4t64", "8.14.1-2")]
    assert evaluate_image_premises(premises, packages, []) == []


def test_declared_min_version_passes_at_or_above_minimum() -> None:
    premises: dict[str, ImagePremise] = {"CVE-2006-2691": DeclaredMinVersion("amule", "2.1.2")}
    assert evaluate_image_premises(premises, [], [DeclaredComponent("amule", "2.1.2")]) == []


def test_declared_min_version_fails_below_minimum() -> None:
    premises: dict[str, ImagePremise] = {"CVE-2006-2691": DeclaredMinVersion("amule", "2.1.2")}
    assert evaluate_image_premises(premises, [], [DeclaredComponent("amule", "2.1.1")]) == [
        ClaimProblem("CVE-2006-2691", "declared amule 2.1.1 is below 2.1.2")
    ]


def test_declared_min_version_ignores_a_dpkg_package_of_the_same_name() -> None:
    # Namespaces stay apart: an old deb named "amule" is not the declared component.
    premises: dict[str, ImagePremise] = {"CVE-2006-2691": DeclaredMinVersion("amule", "2.1.2")}
    assert evaluate_image_premises(premises, [DpkgPackage("amule", "2.1.1-1")], []) == []


def test_declared_min_version_passes_vacuously_when_component_absent() -> None:
    premises: dict[str, ImagePremise] = {"CVE-2006-2691": DeclaredMinVersion("amule", "2.1.2")}
    assert evaluate_image_premises(premises, [], [DeclaredComponent("other", "1.0")]) == []
