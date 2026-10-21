from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePath

from vex_checks.domain.sbom_components import DeclaredComponent, DpkgPackage
from vex_checks.domain.violations import Violation
from vex_checks.ports.driven.sarif_writer import SarifWriter
from vex_checks.ports.driven.sbom_reader import SbomReader
from vex_checks.ports.driven.vex_reader import VexReader


class FakeVexReader(VexReader):
    """Reads the same claims from any VEX file."""

    def __init__(self, claims: dict[str, str]) -> None:
        self._claims = claims

    def read_claims(self, vex_path: PurePath) -> dict[str, str]:
        return dict(self._claims)


class FakeSbomReader(SbomReader):
    """Reads the same components from any SBOM."""

    def __init__(
        self,
        *,
        dpkg_packages: Sequence[DpkgPackage] = (),
        declared_components: Sequence[DeclaredComponent] = (),
    ) -> None:
        self._dpkg_packages = dpkg_packages
        self._declared_components = declared_components

    def read_dpkg_packages(self, sbom_path: PurePath) -> list[DpkgPackage]:
        return list(self._dpkg_packages)

    def read_declared_components(self, sbom_path: PurePath) -> list[DeclaredComponent]:
        return list(self._declared_components)


@dataclass(frozen=True)
class WrittenSarif:
    sarif_path: PurePath
    rule_id: str
    violations: tuple[Violation, ...]
    vex_relpath: str


class FakeSarifWriter(SarifWriter):
    """Records each report it is asked to write."""

    def __init__(self) -> None:
        self.written_sarifs: list[WrittenSarif] = []

    def write_violations(
        self, sarif_path: PurePath, rule_id: str, violations: Sequence[Violation], vex_relpath: str
    ) -> None:
        self.written_sarifs.append(
            WrittenSarif(sarif_path, rule_id, tuple(violations), vex_relpath)
        )
