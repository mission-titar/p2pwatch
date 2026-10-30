"""``AppliedClaimsChecker``: flags the claims of a VEX a vulnerability scan does not apply."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import PurePath

from vex_checks.domain.claim_problem import ClaimProblem


@dataclass(kw_only=True, frozen=True)
class AppliedClaimsReport:
    problems: tuple[ClaimProblem, ...]
    vex_location: str  # where every problem points, as `locate_vex` names it


class AppliedClaimsChecker(ABC):
    """Checks that Grype reports each claim of a VEX and suppresses every match of it, writing a
    SARIF report of the problems when given a path."""

    @abstractmethod
    def check_applied_claims(
        self, sbom_path: PurePath, *, vex_path: PurePath, sarif_path: PurePath | None
    ) -> AppliedClaimsReport:
        """The claims the scan of the SBOM with the VEX does not report, or leaves unsuppressed."""
