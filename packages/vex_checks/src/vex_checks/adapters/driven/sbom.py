from typing import assert_never

from packaging.version import Version

from vex_checks.domain.descriptors import (
    DeclaredMinVersion,
    DpkgMinVersion,
    DpkgPackageAbsent,
    ImagePremise,
)
from vex_checks.domain.sbom_components import DeclaredComponent, DpkgPackage
from vex_checks.domain.violations import Violation


def _upstream(version: str) -> str:
    """The upstream part of a Debian ``[epoch:]upstream[-revision]`` version.

    Epoch and revision are packaging, not code, so a version claim ignores them.

    ponytail: compared as a Python version; a "~rc1" upstream would raise. Swap in a
    real Debian comparator the day one shows up.
    """
    _, _, without_epoch = version.rpartition(":")
    upstream, _, _ = without_epoch.rpartition("-")
    return upstream or without_epoch


def evaluate_image_premises(
    premises: dict[str, ImagePremise],
    packages: list[DpkgPackage],
    declared_components: list[DeclaredComponent],
) -> list[Violation]:
    by_name: dict[str, list[DpkgPackage]] = {}
    for pkg in packages:
        by_name.setdefault(pkg.name, []).append(pkg)
    violations: list[Violation] = []
    for advisory_id, premise in premises.items():
        match premise:
            case DpkgPackageAbsent(package):
                if package in by_name:
                    violations.append(
                        Violation(advisory_id, f"dpkg package {package!r} is present", "security")
                    )
            case DpkgMinVersion(package, minimum):
                for pkg in by_name.get(package, []):
                    if Version(_upstream(pkg.version)) < Version(minimum):
                        violations.append(
                            Violation(
                                advisory_id,
                                f"{package} {pkg.version} is below {minimum}",
                                "security",
                            )
                        )
            case DeclaredMinVersion(component, minimum):
                for declared_component in (c for c in declared_components if c.name == component):
                    if Version(declared_component.version) < Version(minimum):
                        violations.append(
                            Violation(
                                advisory_id,
                                f"declared {component} {declared_component.version}"
                                f" is below {minimum}",
                                "security",
                            )
                        )
            case _:  # pragma: no cover
                assert_never(premise)
    return violations
