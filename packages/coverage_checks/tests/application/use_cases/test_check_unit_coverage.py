"""CheckUnitCoverage: each module's code run by its own tests, over the package's tree."""

from pathlib import PurePath

from coverage_checks.application.ports.driving.unit_coverage_checker import UnitCoverageReport
from coverage_checks.application.use_cases.check_unit_coverage import CheckUnitCoverage
from coverage_checks.domain.own_tests import UnmappedTestFile
from coverage_checks.domain.package_tree import PackageTree
from coverage_checks.domain.shortfall import Shortfall
from coverage_checks.domain.test_coverage import TestCoverage
from tests.fakes.adapters.driven.fake_package_tree_reader import FakePackageTreeReader
from tests.fakes.adapters.driven.fake_test_coverage_reader import FakeTestCoverageReader

LONELY = PurePath("src/pkg/lonely.py")
OTHER = PurePath("src/pkg/other.py")
SIZES = PurePath("src/pkg/sizes.py")
OTHER_TESTS = PurePath("tests/test_other.py")
SIZES_TESTS = PurePath("tests/test_sizes.py")
MIGRATION_TESTS = PurePath("tests/test_migration.py")

FUNCTION_SOURCE = "def run():\n    return 1\n"


def _test_coverage(*, statements_run_by_own_tests: set[int]) -> TestCoverage:
    """`FUNCTION_SOURCE`'s test coverage, its `def` run at import."""
    return TestCoverage(
        statements=frozenset({1, 2}),
        branches=frozenset(),
        statements_run=frozenset({1, 2}),
        branches_run=frozenset(),
        statements_run_by_own_tests=frozenset(statements_run_by_own_tests),
        branches_run_by_own_tests=frozenset(),
    )


def _checker(
    test_files: tuple[PurePath, ...], test_coverage_reader: FakeTestCoverageReader
) -> CheckUnitCoverage:
    return CheckUnitCoverage(
        package_tree_reader=FakePackageTreeReader(
            PackageTree(
                modules=(SIZES, OTHER, LONELY),
                test_files=test_files,
                tests_without_unit={MIGRATION_TESTS.as_posix(): "its subject is SQL"},
            ),
            dict.fromkeys((LONELY, OTHER, SIZES), FUNCTION_SOURCE),
        ),
        test_coverage_reader=test_coverage_reader,
    )


def test_the_report_holds_the_tree_s_problems_then_each_short_module_s_with_the_counts() -> None:
    test_coverage_reader = FakeTestCoverageReader(
        {
            LONELY: _test_coverage(statements_run_by_own_tests=set()),
            OTHER: _test_coverage(statements_run_by_own_tests=set()),
            SIZES: _test_coverage(statements_run_by_own_tests={2}),
        }
    )
    test_files = (
        SIZES_TESTS,
        OTHER_TESTS,
        PurePath("tests/test_nothing.py"),
        MIGRATION_TESTS,
    )

    report = _checker(test_files, test_coverage_reader).check_unit_coverage()

    assert report == UnitCoverageReport(
        problems=(
            UnmappedTestFile(PurePath("tests/test_nothing.py")),
            Shortfall(LONELY, own_test_files=(), unrun_statements=(2,), unrun_branches=()),
            Shortfall(
                OTHER, own_test_files=(OTHER_TESTS,), unrun_statements=(2,), unrun_branches=()
            ),
        ),
        module_count=3,
        tested_module_count=2,
        mapped_test_count=2,
        listed_test_count=1,
        short_module_count=2,
    )
    assert test_coverage_reader.own_test_files_by_module == {
        LONELY: (),
        OTHER: (OTHER_TESTS,),
        SIZES: (SIZES_TESTS,),
    }


def test_a_package_whose_modules_their_own_tests_run_whole_has_no_problem() -> None:
    test_coverage_reader = FakeTestCoverageReader(
        dict.fromkeys((LONELY, OTHER, SIZES), _test_coverage(statements_run_by_own_tests={2}))
    )

    report = _checker((SIZES_TESTS, MIGRATION_TESTS), test_coverage_reader).check_unit_coverage()

    assert report == UnitCoverageReport(
        problems=(),
        module_count=3,
        tested_module_count=1,
        mapped_test_count=1,
        listed_test_count=1,
        short_module_count=0,
    )


def test_a_package_without_a_module_still_reads_its_run_s_coverage() -> None:
    test_coverage_reader = FakeTestCoverageReader({})
    checker = CheckUnitCoverage(
        package_tree_reader=FakePackageTreeReader(
            PackageTree(modules=(), test_files=(), tests_without_unit={}), {}
        ),
        test_coverage_reader=test_coverage_reader,
    )

    report = checker.check_unit_coverage()

    assert report.module_count == 0
    # Read with no module to read, the run's coverage is refused when broken (the reader's tests).
    assert test_coverage_reader.own_test_files_by_module == {}
