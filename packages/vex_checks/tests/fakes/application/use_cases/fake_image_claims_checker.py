from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePath

from vex_checks.application.ports.driving.image_claims_checker import (
    ImageClaimsChecker,
    ImageClaimsReport,
)
from vex_checks.domain.violations import Violation


@dataclass(frozen=True)
class ImageClaimsCheck:
    sbom_path: PurePath
    vex_path: PurePath
    sarif_path: PurePath | None


class FakeImageClaimsChecker(ImageClaimsChecker):
    """Records each check it is asked for, and answers the same problems to each."""

    def __init__(self, problems: Sequence[Violation] = ()) -> None:
        self._problems = tuple(problems)
        self.checks: list[ImageClaimsCheck] = []

    def check_image_claims(
        self, sbom_path: PurePath, vex_path: PurePath, sarif_path: PurePath | None
    ) -> ImageClaimsReport:
        self.checks.append(ImageClaimsCheck(sbom_path, vex_path, sarif_path))
        return ImageClaimsReport(problems=self._problems)
