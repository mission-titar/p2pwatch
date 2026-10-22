from collections.abc import Sequence

from vex_checks.application.ports.driving.claim_coverage_checker import (
    ClaimCoverageChecker,
    ClaimCoverageReport,
)
from vex_checks.domain.broken_input_error import BrokenInputError
from vex_checks.domain.claim_problem import ClaimProblem


class FakeClaimCoverageChecker(ClaimCoverageChecker):
    """Counts the checks it is asked for, and answers the same problems to each, or raises
    ``broken_input_error`` when given one."""

    def __init__(
        self,
        problems: Sequence[ClaimProblem] = (),
        broken_input_error: BrokenInputError | None = None,
    ) -> None:
        self._problems = tuple(problems)
        self._broken_input_error = broken_input_error
        self.check_count = 0

    def check_claim_coverage(self) -> ClaimCoverageReport:
        self.check_count += 1
        if self._broken_input_error is not None:
            raise self._broken_input_error
        return ClaimCoverageReport(problems=self._problems)
