from collections.abc import Mapping, Sequence
from pathlib import PurePath

from coverage_checks.application.ports.driven.test_coverage_reader import TestCoverageReader
from coverage_checks.domain.test_coverage import TestCoverage


class FakeTestCoverageReader(TestCoverageReader):
    """Reads each module's test coverage from ``test_coverage_by_module``, recording the own test
    files it is given for it."""

    def __init__(self, test_coverage_by_module: Mapping[PurePath, TestCoverage]) -> None:
        self._test_coverage_by_module = test_coverage_by_module
        self.own_test_files_by_module: dict[PurePath, tuple[PurePath, ...]] = {}

    def read_test_coverage(
        self, module: PurePath, own_test_files: Sequence[PurePath]
    ) -> TestCoverage:
        self.own_test_files_by_module[module] = tuple(own_test_files)
        return self._test_coverage_by_module[module]
