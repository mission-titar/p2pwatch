"""The command line: parses a subcommand, calls its check, prints its report."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from coverage_checks.application.ports.driving.unit_coverage_checker import (
    NoPerTestCoverage,
    UnitCoverageChecker,
)


class ArgparseCommandLine:
    """``unit-coverage``, run once the package's pytest has recorded coverage in ``data_file``."""

    def __init__(
        self, *, unit_coverage_checker: UnitCoverageChecker, package_name: str, data_file: Path
    ) -> None:
        self._unit_coverage_checker = unit_coverage_checker
        self._package_name = package_name
        self._data_file = data_file

    def run(self, argv: Sequence[str]) -> int:
        """Runs the subcommand ``argv`` names, returns its exit code."""
        parser = argparse.ArgumentParser(
            prog="coverage_checks", description="check each module is covered by its own tests"
        )
        subparsers = parser.add_subparsers(dest="command", required=True)
        subparsers.add_parser(
            "unit-coverage", help="check each module's code is run by its own tests"
        )
        parser.parse_args(argv)
        return self._check_unit_coverage()

    def _check_unit_coverage(self) -> int:
        """Prints each problem and the package's summary, returns 1 on any problem."""
        report = self._unit_coverage_checker.check_unit_coverage()
        if isinstance(report, NoPerTestCoverage):
            print(
                f"no per-test branch coverage in {self._data_file}: run this package's pytest"
                " first, with branch coverage and --cov-context=test",
                file=sys.stderr,
            )
            return 1
        for problem in report.problems:
            print(problem)
        print(
            f"{self._package_name}: {report.mapped_test_count} test files map to"
            f" {report.tested_module_count} of {report.module_count} modules,"
            f" {report.listed_test_count} are listed without a unit; {report.short_module_count} of"
            f" {report.module_count} modules short of their own tests"
        )
        return 1 if report.problems else 0
