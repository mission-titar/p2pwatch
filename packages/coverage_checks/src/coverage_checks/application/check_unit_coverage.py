"""Checks each module of the package is run by its own tests, what an import runs aside."""

from coverage_checks.domain.own_tests import find_own_tests
from coverage_checks.domain.shortfall import find_shortfall
from coverage_checks.ports.driven.package_tree_reader import PackageTreeReader
from coverage_checks.ports.driven.test_coverage_reader import TestCoverageReader
from coverage_checks.ports.driving.unit_coverage_checker import (
    NoPerTestCoverage,
    UnitCoverageChecker,
    UnitCoverageReport,
)


class CheckUnitCoverage(UnitCoverageChecker):
    """Over the package's tree and the coverage its pytest recorded."""

    def __init__(
        self, *, package_tree_reader: PackageTreeReader, test_coverage_reader: TestCoverageReader
    ) -> None:
        self._package_tree_reader = package_tree_reader
        self._test_coverage_reader = test_coverage_reader

    def check_unit_coverage(self) -> UnitCoverageReport | NoPerTestCoverage:
        if not self._test_coverage_reader.has_per_test_branch_coverage():
            return NoPerTestCoverage()
        own_tests = find_own_tests(self._package_tree_reader.read_package_tree())
        shortfalls = [
            shortfall
            for module, test_files in own_tests.test_files_by_module.items()
            if (
                shortfall := find_shortfall(
                    module,
                    test_files,
                    self._test_coverage_reader.read_test_coverage(module, test_files),
                    self._package_tree_reader.read_module_source(module),
                )
            )
        ]
        return UnitCoverageReport(
            problems=(*own_tests.problems, *shortfalls),
            module_count=len(own_tests.test_files_by_module),
            tested_module_count=sum(
                1 for test_files in own_tests.test_files_by_module.values() if test_files
            ),
            mapped_test_count=own_tests.mapped_test_count,
            listed_test_count=own_tests.listed_test_count,
            short_module_count=len(shortfalls),
        )
