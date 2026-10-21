from collections.abc import Mapping, Sequence
from pathlib import PurePath

from coverage_checks.domain.package_tree import PackageTree
from coverage_checks.domain.test_coverage import TestCoverage
from coverage_checks.ports.driven.package_tree_reader import PackageTreeReader
from coverage_checks.ports.driven.test_coverage_reader import TestCoverageReader
from coverage_checks.ports.driving.unit_coverage_checker import (
    NoPerTestCoverage,
    UnitCoverageChecker,
    UnitCoverageReport,
)


class FakePackageTreeReader(PackageTreeReader):
    """Reads the tree it is given, and each module's source from ``sources_by_module``."""

    def __init__(
        self, package_tree: PackageTree, sources_by_module: Mapping[PurePath, str]
    ) -> None:
        self._package_tree = package_tree
        self._sources_by_module = sources_by_module

    def read_package_tree(self) -> PackageTree:
        return self._package_tree

    def read_module_source(self, module: PurePath) -> str:
        return self._sources_by_module[module]


class FakeTestCoverageReader(TestCoverageReader):
    """Reads each module's test coverage from ``test_coverage_by_module``, recording the own test
    files it is given for it."""

    def __init__(
        self,
        test_coverage_by_module: Mapping[PurePath, TestCoverage],
        *,
        has_per_test_branch_coverage: bool = True,
    ) -> None:
        self._test_coverage_by_module = test_coverage_by_module
        self._has_per_test_branch_coverage = has_per_test_branch_coverage
        self.own_test_files_by_module: dict[PurePath, tuple[PurePath, ...]] = {}

    def has_per_test_branch_coverage(self) -> bool:
        return self._has_per_test_branch_coverage

    def read_test_coverage(
        self, module: PurePath, own_test_files: Sequence[PurePath]
    ) -> TestCoverage:
        self.own_test_files_by_module[module] = tuple(own_test_files)
        return self._test_coverage_by_module[module]


class FakeUnitCoverageChecker(UnitCoverageChecker):
    """Answers the outcome it is given, counting its checks."""

    def __init__(self, outcome: UnitCoverageReport | NoPerTestCoverage) -> None:
        self._outcome = outcome
        self.check_count = 0

    def check_unit_coverage(self) -> UnitCoverageReport | NoPerTestCoverage:
        self.check_count += 1
        return self._outcome
