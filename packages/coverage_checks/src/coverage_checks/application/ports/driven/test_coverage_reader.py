from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import PurePath

from coverage_checks.domain.test_coverage import TestCoverage


class TestCoverageReader(ABC):
    """Reads the statements and branches each test of the package's run ran."""

    __test__ = False  # not a test class, where a test module imports it

    @abstractmethod
    def read_test_coverage(
        self, module: PurePath, own_test_files: Sequence[PurePath]
    ) -> TestCoverage:
        """*module*'s test coverage, its own tests being those of *own_test_files*; a run that
        recorded no branches, or no test apart, is a broken input."""
