from collections.abc import Mapping, Sequence
from pathlib import PurePath

from coverage_checks.application.ports.driven.test_coverage_reader import TestCoverageReader
from coverage_checks.domain.test_coverage import TestCoverage


class FakeTestCoverageReader(TestCoverageReader):
    """Reads each module's test coverage from ``test_coverage_by_module``, recording the own test
    files it is asked them for: ``None`` until it is read."""

    def __init__(self, test_coverage_by_module: Mapping[PurePath, TestCoverage]) -> None:
        self._test_coverage_by_module = test_coverage_by_module
        self.own_test_files_by_module: dict[PurePath, tuple[PurePath, ...]] | None = None

    def read_test_coverage_by_module(
        self, own_test_files_by_module: Mapping[PurePath, Sequence[PurePath]]
    ) -> dict[PurePath, TestCoverage]:
        self.own_test_files_by_module = {
            module: tuple(own_test_files)
            for module, own_test_files in own_test_files_by_module.items()
        }
        return {
            module: self._test_coverage_by_module[module] for module in own_test_files_by_module
        }
