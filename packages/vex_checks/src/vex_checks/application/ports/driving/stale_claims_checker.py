"""``StaleClaimsChecker``: flags the claims of a VEX a vulnerability scan no longer reports."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import PurePath

from vex_checks.domain.violations import Violation


@dataclass(frozen=True)
class StaleClaimsReport:
    problems: tuple[Violation, ...]  # each located at the VEX


class StaleClaimsChecker(ABC):
    """Checks a VEX's claims are still reported, writing a SARIF report of the problems when given
    a path."""

    @abstractmethod
    def check_stale_claims(
        self, sbom_path: PurePath, vex_path: PurePath, sarif_path: PurePath | None
    ) -> StaleClaimsReport:
        """The claims whose advisory the scan of the SBOM no longer reports."""
