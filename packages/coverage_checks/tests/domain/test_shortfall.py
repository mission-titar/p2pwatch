"""Tests for what of a module its own tests leave unrun, the top-level code the run ran aside."""

from pathlib import PurePath

from coverage_checks.domain.shortfall import find_shortfall
from coverage_checks.domain.test_coverage import Branch, TestCoverage

SIZES = """\
LIMIT = 10


def is_short(size):
    if size < LIMIT:
        return True
    return False
"""

SIZES_STATEMENTS = {1, 4, 5, 6, 7}
SIZES_BRANCHES: set[Branch] = {(5, 6), (5, 7)}


def _test_coverage(
    statements: set[int],
    branches: set[Branch],
    *,
    run: tuple[set[int], set[Branch]],
    run_by_own_tests: tuple[set[int], set[Branch]],
) -> TestCoverage:
    return TestCoverage(
        statements=frozenset(statements),
        branches=frozenset(branches),
        statements_run=frozenset(run[0]),
        branches_run=frozenset(run[1]),
        statements_run_by_own_tests=frozenset(run_by_own_tests[0]),
        branches_run_by_own_tests=frozenset(run_by_own_tests[1]),
    )


def test_a_module_its_own_tests_run_whole_has_no_shortfall() -> None:
    # The import ran the top-level statements under no test's context.
    test_coverage = _test_coverage(
        SIZES_STATEMENTS,
        SIZES_BRANCHES,
        run=(SIZES_STATEMENTS, SIZES_BRANCHES),
        run_by_own_tests=({5, 6, 7}, SIZES_BRANCHES),
    )
    shortfall = find_shortfall(
        PurePath("src/pkg/sizes.py"), (PurePath("tests/test_sizes.py"),), test_coverage, SIZES
    )
    assert shortfall is None


def test_what_only_another_module_s_test_runs_is_short_naming_its_own_tests() -> None:
    test_coverage = _test_coverage(
        SIZES_STATEMENTS,
        SIZES_BRANCHES,
        run=(SIZES_STATEMENTS, SIZES_BRANCHES),
        run_by_own_tests=({5, 6}, {(5, 6)}),
    )
    shortfall = find_shortfall(
        PurePath("src/pkg/sizes.py"),
        (PurePath("tests/test_sizes.py"), PurePath("tests/test_sizes_more.py")),
        test_coverage,
        SIZES,
    )
    assert shortfall == (
        "src/pkg/sizes.py: statements 7 and branches 5->7 run by none of its own tests"
        " (tests/test_sizes.py, tests/test_sizes_more.py)"
    )


def test_a_function_of_a_module_without_own_tests_is_short() -> None:
    test_coverage = _test_coverage(
        SIZES_STATEMENTS,
        SIZES_BRANCHES,
        run=(SIZES_STATEMENTS, SIZES_BRANCHES),
        run_by_own_tests=(set(), set()),
    )
    assert find_shortfall(PurePath("src/pkg/sizes.py"), (), test_coverage, SIZES) == (
        "src/pkg/sizes.py: statements 5, 6, 7 and branches 5->6, 5->7 run by none of its own"
        " tests (it has none)"
    )


def test_a_top_level_statement_and_branch_no_test_runs_are_short() -> None:
    widths = """\
import sys

if sys.maxsize > 0:
    WIDTH = 64
else:
    WIDTH = 32


def width():
    return WIDTH
"""
    test_coverage = _test_coverage(
        {1, 3, 4, 6, 9, 10},
        {(3, 4), (3, 6)},
        run=({1, 3, 4, 9, 10}, {(3, 4)}),
        run_by_own_tests=({10}, set()),
    )
    shortfall = find_shortfall(
        PurePath("src/pkg/widths.py"), (PurePath("tests/test_widths.py"),), test_coverage, widths
    )
    assert shortfall == (
        "src/pkg/widths.py: statements 6 and branches 3->6 run by none of its own tests"
        " (tests/test_widths.py)"
    )


def test_a_branch_to_the_function_s_exit_reads_exit() -> None:
    names = """\
def record(names, name):
    if name:
        names.append(name)
"""
    test_coverage = _test_coverage(
        {1, 2, 3},
        {(2, 3), (2, -1)},
        run=({1, 2, 3}, {(2, 3), (2, -1)}),
        run_by_own_tests=({2, 3}, {(2, 3)}),
    )
    shortfall = find_shortfall(
        PurePath("src/pkg/names.py"), (PurePath("tests/test_names.py"),), test_coverage, names
    )
    assert shortfall == (
        "src/pkg/names.py: branches 2->exit run by none of its own tests (tests/test_names.py)"
    )
