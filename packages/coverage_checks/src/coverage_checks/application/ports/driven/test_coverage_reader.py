from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from pathlib import PurePath

from coverage_checks.domain.test_coverage import TestCoverage


class TestCoverageReader(ABC):
    """Reads the statements and branches each test of the package's run ran."""

    __test__ = False  # not a test class, where a test module imports it

    @abstractmethod
    def read_test_coverage_by_module(
        self, own_test_files_by_module: Mapping[PurePath, Sequence[PurePath]]
    ) -> dict[PurePath, TestCoverage]:
        """Each module's test coverage, its own tests those of its test files; a run that recorded
        no branches, or no test apart, is a broken input, even with no module to read."""
