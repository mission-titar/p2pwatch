"""Each module's statements and branches are run by its own tests, what an import runs aside.

Run in a package's directory, once its pytest has recorded per-test contexts (`--cov-context`).
"""

import sys
from pathlib import Path

from coverage_checks.ports.driving.unit_coverage_checker import (
    NoPerTestCoverage,
    UnitCoverageChecker,
)


def main(*, unit_coverage_checker: UnitCoverageChecker) -> int:
    """Prints each problem and a summary, returns 1 on any problem."""
    report = unit_coverage_checker.check_unit_coverage()
    if isinstance(report, NoPerTestCoverage):
        print(
            "no per-test branch coverage in .coverage: run this"
            " package's pytest first, with branch coverage and --cov-context=test",
            file=sys.stderr,
        )
        return 1
    for problem in report.problems:
        print(problem)
    print(
        f"{Path.cwd().name}: {report.mapped_test_count} test files map to"
        f" {report.tested_module_count} of {report.module_count} modules,"
        f" {report.listed_test_count} are listed without a unit; {report.short_module_count} of"
        f" {report.module_count} modules short of their own tests"
    )
    return 1 if report.problems else 0
