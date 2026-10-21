"""``UnitCoverageChecker``: checks each module's code is run by its own tests."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class UnitCoverageReport:
    """What is wrong, the tree's problems first, and the counts of the package's summary."""

    problems: tuple[str, ...]
    module_count: int
    tested_module_count: int  # the modules with at least one own test file
    mapped_test_count: int
    listed_test_count: int  # the test files listed in `tests_without_unit`
    short_module_count: int


@dataclass(frozen=True)
class NoPerTestCoverage:
    """The run recorded no branches, or no test apart: there is nothing to check."""


class UnitCoverageChecker(ABC):
    """Checks the package's modules against the coverage its pytest recorded, test by test."""

    @abstractmethod
    def check_unit_coverage(self) -> UnitCoverageReport | NoPerTestCoverage:
        """The test files that test no module, and what of each module its own tests leave
        unrun but what its import ran."""
