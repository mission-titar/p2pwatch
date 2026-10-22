from coverage_checks.application.ports.driving.unit_coverage_checker import (
    NoPerTestCoverage,
    UnitCoverageChecker,
    UnitCoverageReport,
)


class FakeUnitCoverageChecker(UnitCoverageChecker):
    """Answers the outcome it is given, counting its checks."""

    def __init__(self, outcome: UnitCoverageReport | NoPerTestCoverage) -> None:
        self._outcome = outcome
        self.check_count = 0

    def check_unit_coverage(self) -> UnitCoverageReport | NoPerTestCoverage:
        self.check_count += 1
        return self._outcome
