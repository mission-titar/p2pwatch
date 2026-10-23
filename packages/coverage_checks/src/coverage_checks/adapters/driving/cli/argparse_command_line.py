"""The command line: parses a subcommand, calls its check, prints its report."""

import argparse
import sys
from collections.abc import Sequence
from typing import assert_never

from coverage_checks.application.ports.driving.unit_coverage_checker import (
    UnitCoverageChecker,
    UnitCoverageProblem,
)
from coverage_checks.domain.broken_input_error import BrokenInputError
from coverage_checks.domain.own_tests import (
    ListedTestOfModule,
    ListingWithoutReason,
    StaleListing,
    UnitNameCollision,
    UnmappedTestFile,
)
from coverage_checks.domain.shortfall import Shortfall


class ArgparseCommandLine:
    """``unit-coverage``, run once the package's pytest has recorded its coverage."""

    def __init__(self, *, unit_coverage_checker: UnitCoverageChecker, package_name: str) -> None:
        self._unit_coverage_checker = unit_coverage_checker
        self._package_name = package_name

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
        """Prints each problem and the package's summary, returns 1 on any problem or a broken
        input."""
        try:
            report = self._unit_coverage_checker.check_unit_coverage()
        except BrokenInputError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        for problem in report.problems:
            print(_problem_line(problem))
        print(
            f"{self._package_name}: {report.mapped_test_count} test files map to"
            f" {report.tested_module_count} of {report.module_count} modules,"
            f" {report.listed_test_count} are listed without a unit; {report.short_module_count} of"
            f" {report.module_count} modules short of their own tests"
        )
        return 1 if report.problems else 0


def _problem_line(problem: UnitCoverageProblem) -> str:
    """The line naming *problem*'s file and what is wrong with it."""
    match problem:
        case ListingWithoutReason(listed_path):
            return f"{listed_path}: listed in tests_without_unit without its reason"
        case UnitNameCollision(module):
            return (
                f"{module.as_posix()}: its tests would be named like those of"
                f" __{module.stem}__.py beside it; rename it"
            )
        case ListedTestOfModule(test_file, module):
            return (
                f"{test_file.as_posix()}: listed in tests_without_unit, but tests"
                f" {module.as_posix()}"
            )
        case UnmappedTestFile(test_file):
            return (
                f"{test_file.as_posix()}: tests no module of src; name it after the module it"
                " tests, or list it in [tool.coverage_checks] tests_without_unit with its reason"
            )
        case StaleListing(listed_path):
            return f"{listed_path}: listed in tests_without_unit, but names no test file"
        case Shortfall():
            return _shortfall_line(problem)
        case _:  # pragma: no cover
            assert_never(problem)


def _shortfall_line(shortfall: Shortfall) -> str:
    """The line naming the module, what its own tests leave unrun, and those own tests."""
    unrun = [
        f"{kind} {', '.join(labels)}"
        for kind, labels in (
            ("statements", [str(statement) for statement in shortfall.unrun_statements]),
            (
                "branches",
                [
                    f"{start}->{end if end > 0 else 'exit'}"
                    for start, end in shortfall.unrun_branches
                ],
            ),
        )
        if labels
    ]
    own_test_names = (
        ", ".join(test_file.as_posix() for test_file in shortfall.own_test_files) or "it has none"
    )
    return (
        f"{shortfall.module.as_posix()}: {' and '.join(unrun)} run by none of its own tests"
        f" ({own_test_names})"
    )
