from dataclasses import dataclass

type Branch = tuple[int, int]


@dataclass(kw_only=True, frozen=True)
class TestCoverage:
    """A module's statements and branches, those the test run ran and those its own tests ran.

    The test run includes what its imports ran, under no test; a branch's end is negative when it
    leaves the function."""

    __test__ = False  # not a test class, where a test module imports it

    statements: frozenset[int]
    branches: frozenset[Branch]
    statements_run: frozenset[int]
    branches_run: frozenset[Branch]
    statements_run_by_own_tests: frozenset[int]
    branches_run_by_own_tests: frozenset[Branch]
