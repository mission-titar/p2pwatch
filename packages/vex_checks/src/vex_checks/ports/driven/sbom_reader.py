from abc import ABC, abstractmethod
from pathlib import PurePath

from vex_checks.domain.sbom_components import DeclaredComponent, DpkgPackage


class SbomReader(ABC):
    """Reads an image's SBOM."""

    @abstractmethod
    def read_dpkg_packages(self, sbom_path: PurePath) -> list[DpkgPackage]:
        """The packages dpkg installed, in document order."""

    @abstractmethod
    def read_declared_components(self, sbom_path: PurePath) -> list[DeclaredComponent]:
        """The components declared by hand (aMule), in document order."""
