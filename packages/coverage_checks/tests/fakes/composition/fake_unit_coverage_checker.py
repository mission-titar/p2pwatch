from coverage_checks.application.ports.driving.unit_coverage_checker import (
    UnitCoverageChecker,
    UnitCoverageReport,
)
from coverage_checks.domain.broken_input_error import BrokenInputError


class FakeUnitCoverageChecker(UnitCoverageChecker):
    """Answers the report it is given, or raises its broken input, counting its checks."""

    def __init__(
        self,
        unit_coverage_report: UnitCoverageReport,
        *,
        broken_input: BrokenInputError | None = None,
    ) -> None:
        self._unit_coverage_report = unit_coverage_report
        self._broken_input = broken_input
        self.check_count = 0

    def check_unit_coverage(self) -> UnitCoverageReport:
        self.check_count += 1
        if self._broken_input is not None:
            raise self._broken_input
        return self._unit_coverage_report
