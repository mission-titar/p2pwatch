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
    premises: dict[str, ImagePremise] = {"CVE-2024-0001": DpkgPackageAbsent(package="libcurl4")}
    packages = [DpkgPackage(name="libcurl4t64", version="8.14.1-2")]
    assert evaluate_image_premises(premises, packages=packages, declared_components=[]) == []


def test_package_absent_fails_when_package_present() -> None:
    premises: dict[str, ImagePremise] = {"CVE-2024-0001": DpkgPackageAbsent(package="libcurl4")}
    packages = [DpkgPackage(name="libcurl4", version="8.14.1-2")]
    assert evaluate_image_premises(premises, packages=packages, declared_components=[]) == [
        ClaimProblem(advisory_id="CVE-2024-0001", message="dpkg package 'libcurl4' is present")
    ]


def test_package_min_version_passes_at_or_above_minimum() -> None:
    premises: dict[str, ImagePremise] = {
        "CVE-2016-1405": DpkgMinVersion(package="curl", minimum="8.0")
    }
    packages = [DpkgPackage(name="curl", version="8.14.1-2")]
    assert evaluate_image_premises(premises, packages=packages, declared_components=[]) == []


def test_package_min_version_fails_below_minimum() -> None:
    premises: dict[str, ImagePremise] = {
        "CVE-2016-1405": DpkgMinVersion(package="curl", minimum="8.0")
    }
    packages = [DpkgPackage(name="curl", version="7.88.1-10+deb12u5")]
    assert evaluate_image_premises(premises, packages=packages, declared_components=[]) == [
        ClaimProblem(advisory_id="CVE-2016-1405", message="curl 7.88.1-10+deb12u5 is below 8.0")
    ]


def test_package_min_version_compares_the_upstream_part_of_a_debian_version() -> None:
    # Only the upstream part compares; whole, "1:8.14.1-2" is not a valid version.
    premises: dict[str, ImagePremise] = {
        "CVE-2016-1405": DpkgMinVersion(package="curl", minimum="8.14")
    }
    assert (
        evaluate_image_premises(
            premises,
            packages=[DpkgPackage(name="curl", version="1:8.14.1-2")],
            declared_components=[],
        )
        == []
    )


def test_package_min_version_handles_a_version_with_no_revision() -> None:
    # A native Debian package carries no "-revision" at all: the whole string is upstream.
    premises: dict[str, ImagePremise] = {
        "CVE-2016-1405": DpkgMinVersion(package="curl", minimum="8.0")
    }
    assert (
        evaluate_image_premises(
            premises, packages=[DpkgPackage(name="curl", version="8.14.1")], declared_components=[]
        )
        == []
    )


def test_package_min_version_passes_vacuously_when_package_absent() -> None:
    premises: dict[str, ImagePremise] = {
        "CVE-2016-1405": DpkgMinVersion(package="curl", minimum="8.0")
    }
    packages = [DpkgPackage(name="libcurl4t64", version="8.14.1-2")]
    assert evaluate_image_premises(premises, packages=packages, declared_components=[]) == []


def test_declared_min_version_passes_at_or_above_minimum() -> None:
    premises: dict[str, ImagePremise] = {
        "CVE-2006-2691": DeclaredMinVersion(component="amule", minimum="2.1.2")
    }
    assert (
        evaluate_image_premises(
            premises,
            packages=[],
            declared_components=[DeclaredComponent(name="amule", version="2.1.2")],
        )
        == []
    )


def test_declared_min_version_fails_below_minimum() -> None:
    premises: dict[str, ImagePremise] = {
        "CVE-2006-2691": DeclaredMinVersion(component="amule", minimum="2.1.2")
    }
    assert evaluate_image_premises(
        premises,
        packages=[],
        declared_components=[DeclaredComponent(name="amule", version="2.1.1")],
    ) == [ClaimProblem(advisory_id="CVE-2006-2691", message="declared amule 2.1.1 is below 2.1.2")]


def test_declared_min_version_ignores_a_dpkg_package_of_the_same_name() -> None:
    # Namespaces stay apart: an old deb named "amule" is not the declared component.
    premises: dict[str, ImagePremise] = {
        "CVE-2006-2691": DeclaredMinVersion(component="amule", minimum="2.1.2")
    }
    assert (
        evaluate_image_premises(
            premises,
            packages=[DpkgPackage(name="amule", version="2.1.1-1")],
            declared_components=[],
        )
        == []
    )


def test_declared_min_version_passes_vacuously_when_component_absent() -> None:
    premises: dict[str, ImagePremise] = {
        "CVE-2006-2691": DeclaredMinVersion(component="amule", minimum="2.1.2")
    }
    assert (
        evaluate_image_premises(
            premises,
            packages=[],
            declared_components=[DeclaredComponent(name="other", version="1.0")],
        )
        == []
    )
