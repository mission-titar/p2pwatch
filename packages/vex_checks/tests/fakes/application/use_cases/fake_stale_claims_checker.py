from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePath

from vex_checks.application.ports.driving.stale_claims_checker import (
    StaleClaimsChecker,
    StaleClaimsReport,
)
from vex_checks.domain.claim_problem import ClaimProblem


@dataclass(frozen=True)
class StaleClaimsCheck:
    sbom_path: PurePath
    vex_path: PurePath
    sarif_path: PurePath | None


class FakeStaleClaimsChecker(StaleClaimsChecker):
    """Records each check it is asked for, and answers the same report to each."""

    def __init__(self, problems: Sequence[ClaimProblem] = (), vex_location: str = "") -> None:
        self._problems = tuple(problems)
        self._vex_location = vex_location
        self.checks: list[StaleClaimsCheck] = []

    def check_stale_claims(
        self, sbom_path: PurePath, vex_path: PurePath, sarif_path: PurePath | None
    ) -> StaleClaimsReport:
        self.checks.append(StaleClaimsCheck(sbom_path, vex_path, sarif_path))
        return StaleClaimsReport(problems=self._problems, vex_location=self._vex_location)
