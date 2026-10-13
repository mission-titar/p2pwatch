import json
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from packaging.version import Version

from vex_guards.descriptors import (
    DeclaredMinVersion,
    DpkgMinVersion,
    DpkgPackageAbsent,
    ImageGuard,
)
from vex_guards.violations import Violation


@dataclass(frozen=True)
class DpkgPackage:
    name: str
    version: str


def load_dpkg_packages(path: Path) -> list[DpkgPackage]:
    """The dpkg packages of a Syft JSON SBOM, in document order.

    Syft types those "deb". aMule (declared by hand, see ``load_declared_components``)
    and our Python wheels do not come from dpkg, so a dpkg guard ignores them.
    """
    doc = json.loads(path.read_text())
    return [
        DpkgPackage(name=a["name"], version=a["version"])
        for a in doc["artifacts"]
        if a["type"] == "deb"
    ]


@dataclass(frozen=True)
class DeclaredComponent:
    name: str
    version: str


def load_declared_components(path: Path) -> list[DeclaredComponent]:
    """The components declared by hand (aMule) of a Syft JSON SBOM, in document order.

    They are the artifacts with a ``pkg:generic/`` purl, kept apart from dpkg names.
    """
    doc = json.loads(path.read_text())
    return [
        DeclaredComponent(name=a["name"], version=a["version"])
        for a in doc["artifacts"]
        if a.get("purl", "").startswith("pkg:generic/")
    ]


def _upstream(version: str) -> str:
    """The upstream part of a Debian ``[epoch:]upstream[-revision]`` version.

    Epoch and revision are packaging, not code, so a version claim ignores them.

    ponytail: compared as a Python version; a "~rc1" upstream would raise. Swap in a
    real Debian comparator the day one shows up.
    """
    _, _, without_epoch = version.rpartition(":")
    upstream, _, _ = without_epoch.rpartition("-")
    return upstream or without_epoch


def evaluate_image_guards(
    guards: dict[str, ImageGuard],
    packages: list[DpkgPackage],
    declared_components: list[DeclaredComponent],
) -> list[Violation]:
    by_name: dict[str, list[DpkgPackage]] = {}
    for pkg in packages:
        by_name.setdefault(pkg.name, []).append(pkg)
    violations: list[Violation] = []
    for advisory_id, guard in guards.items():
        match guard:
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
                assert_never(guard)
    return violations
