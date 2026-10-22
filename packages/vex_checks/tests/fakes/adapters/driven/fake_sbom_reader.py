from collections.abc import Sequence
from pathlib import PurePath

from vex_checks.application.ports.driven.sbom_reader import SbomReader
from vex_checks.domain.sbom_components import DeclaredComponent, DpkgPackage


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
