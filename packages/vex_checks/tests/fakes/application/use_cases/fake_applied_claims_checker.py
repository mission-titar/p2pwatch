from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePath

from vex_checks.application.ports.driving.applied_claims_checker import (
    AppliedClaimsChecker,
    AppliedClaimsReport,
)
from vex_checks.domain.claim_problem import ClaimProblem


@dataclass(frozen=True)
class AppliedClaimsCheck:
    sbom_path: PurePath
    vex_path: PurePath
    sarif_path: PurePath | None


class FakeAppliedClaimsChecker(AppliedClaimsChecker):
    """Records each check it is asked for, and answers the same report to each."""

    def __init__(self, problems: Sequence[ClaimProblem] = (), vex_location: str = "") -> None:
        self._problems = tuple(problems)
        self._vex_location = vex_location
        self.checks: list[AppliedClaimsCheck] = []

    def check_applied_claims(
        self, sbom_path: PurePath, vex_path: PurePath, sarif_path: PurePath | None
    ) -> AppliedClaimsReport:
        self.checks.append(AppliedClaimsCheck(sbom_path, vex_path, sarif_path))
        return AppliedClaimsReport(problems=self._problems, vex_location=self._vex_location)
