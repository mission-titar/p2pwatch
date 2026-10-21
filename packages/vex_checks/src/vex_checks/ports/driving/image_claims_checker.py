"""``ImageClaimsChecker``: checks the image claims of a VEX against a built image's SBOM."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import PurePath

from vex_checks.domain.violations import Violation


@dataclass(frozen=True)
class ImageClaimsReport:
    problems: tuple[Violation, ...]  # each located at the VEX


class ImageClaimsChecker(ABC):
    """Checks a VEX's image claims, writing a SARIF report of the problems when given a path."""

    @abstractmethod
    def check_image_claims(
        self, sbom_path: PurePath, vex_path: PurePath, sarif_path: PurePath | None
    ) -> ImageClaimsReport:
        """The image premises the VEX claims that the SBOM falsifies."""
