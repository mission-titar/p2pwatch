from collections.abc import Sequence

from vex_checks.application.ports.driving.claim_coverage_checker import (
    ClaimCoverageChecker,
    ClaimCoverageProblem,
    ClaimCoverageReport,
)


class FakeClaimCoverageChecker(ClaimCoverageChecker):
    """Counts the checks it is asked for, and answers the same problems to each."""

    def __init__(self, problems: Sequence[ClaimCoverageProblem] = ()) -> None:
        self._problems = tuple(problems)
        self.check_count = 0

    def check_claim_coverage(self) -> ClaimCoverageReport:
        self.check_count += 1
        return ClaimCoverageReport(problems=self._problems)
