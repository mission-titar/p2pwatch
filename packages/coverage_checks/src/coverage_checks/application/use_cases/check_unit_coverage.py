"""Checks each module of the package is run by its own tests, what an import runs aside."""

from coverage_checks.application.ports.driven.package_tree_reader import PackageTreeReader
from coverage_checks.application.ports.driven.test_coverage_reader import TestCoverageReader
from coverage_checks.application.ports.driving.unit_coverage_checker import (
    UnitCoverageChecker,
    UnitCoverageReport,
)
from coverage_checks.domain.own_tests import find_own_tests
from coverage_checks.domain.shortfall import find_shortfall


class CheckUnitCoverage(UnitCoverageChecker):
    """Over the package's tree and the coverage its pytest recorded."""

    def __init__(
        self, *, package_tree_reader: PackageTreeReader, test_coverage_reader: TestCoverageReader
    ) -> None:
        self._package_tree_reader = package_tree_reader
        self._test_coverage_reader = test_coverage_reader

    def check_unit_coverage(self) -> UnitCoverageReport:
        own_tests = find_own_tests(self._package_tree_reader.read_package_tree())
        # Read even with no module, so that a broken run is refused whatever the package holds.
        test_coverage_by_module = self._test_coverage_reader.read_test_coverage_by_module(
            own_tests.test_files_by_module
        )
        shortfalls = [
            shortfall
            for module, test_files in own_tests.test_files_by_module.items()
            if (
                shortfall := find_shortfall(
                    module,
                    own_test_files=test_files,
                    test_coverage=test_coverage_by_module[module],
                    source=self._package_tree_reader.read_module_source(module),
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
