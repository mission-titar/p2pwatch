"""The command line: one subcommand, which prints the unit coverage report of the package."""

from pathlib import PurePath

import pytest

from coverage_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from coverage_checks.application.ports.driving.unit_coverage_checker import (
    UnitCoverageProblem,
    UnitCoverageReport,
)
from coverage_checks.domain.broken_input_error import BrokenInputError
from coverage_checks.domain.own_tests import (
    ListedTestOfModule,
    ListingWithoutReason,
    StaleListing,
    UnitNameCollision,
    UnmappedTestFile,
)
from coverage_checks.domain.shortfall import Shortfall
from tests.fakes.composition.fake_unit_coverage_checker import FakeUnitCoverageChecker

SIZES = PurePath("src/pkg/sizes.py")


def _report(*problems: UnitCoverageProblem) -> UnitCoverageReport:
    return UnitCoverageReport(
        problems=problems,
        module_count=3,
        tested_module_count=2,
        mapped_test_count=4,
        listed_test_count=1,
        short_module_count=len(problems),
    )


def _command_line(unit_coverage_checker: FakeUnitCoverageChecker) -> ArgparseCommandLine:
    return ArgparseCommandLine(unit_coverage_checker=unit_coverage_checker, package_name="pkg")


def test_unit_coverage_prints_each_problem_then_the_package_s_summary_and_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    unit_coverage_checker = FakeUnitCoverageChecker(
        _report(
            StaleListing(listed_path="tests/gone/"), StaleListing(listed_path="tests/test_gone.py")
        )
    )

    assert _command_line(unit_coverage_checker).run(["unit-coverage"]) == 1

    assert capsys.readouterr().out == (
        "tests/gone/: listed in tests_without_unit, but names no test file\n"
        "tests/test_gone.py: listed in tests_without_unit, but names no test file\n"
        "pkg: 4 test files map to 2 of 3 modules, 1 are listed without a unit;"
        " 2 of 3 modules short of their own tests\n"
    )
    assert unit_coverage_checker.check_count == 1


@pytest.mark.parametrize(
    ("problem", "problem_line"),
    [
        (
            ListingWithoutReason(listed_path="tests/test_sql.py"),
            "tests/test_sql.py: listed in tests_without_unit without its reason",
        ),
        (
            UnitNameCollision(module=PurePath("src/pkg/main.py")),
            "src/pkg/main.py: its tests would be named like those of __main__.py beside it;"
            " rename it",
        ),
        (
            ListedTestOfModule(test_file=PurePath("tests/test_sizes.py"), module=SIZES),
            "tests/test_sizes.py: listed in tests_without_unit, but tests src/pkg/sizes.py",
        ),
        (
            UnmappedTestFile(test_file=PurePath("tests/test_nothing.py")),
            "tests/test_nothing.py: tests no module of src; name it after the module it tests,"
            " or list it in [tool.coverage_checks] tests_without_unit with its reason",
        ),
        (
            StaleListing(listed_path="tests/test_gone.py"),
            "tests/test_gone.py: listed in tests_without_unit, but names no test file",
        ),
        (
            Shortfall(
                module=SIZES,
                own_test_files=(PurePath("tests/test_sizes.py"), PurePath("tests/test_sizes_x.py")),
                unrun_statements=(5, 6, 7),
                unrun_branches=((5, 6), (5, 7)),
            ),
            "src/pkg/sizes.py: statements 5, 6, 7 and branches 5->6, 5->7 run by none of its own"
            " tests (tests/test_sizes.py, tests/test_sizes_x.py)",
        ),
        (
            Shortfall(module=SIZES, own_test_files=(), unrun_statements=(7,), unrun_branches=()),
            "src/pkg/sizes.py: statements 7 run by none of its own tests (it has none)",
        ),
        (
            Shortfall(
                module=SIZES,
                own_test_files=(PurePath("tests/test_sizes.py"),),
                unrun_statements=(),
                unrun_branches=((2, -1),),
            ),
            "src/pkg/sizes.py: branches 2->exit run by none of its own tests (tests/test_sizes.py)",
        ),
    ],
)
def test_unit_coverage_words_each_kind_of_problem_on_a_line_of_its_own(
    *, problem: UnitCoverageProblem, problem_line: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _command_line(FakeUnitCoverageChecker(_report(problem))).run(["unit-coverage"]) == 1

    assert capsys.readouterr().out.splitlines()[0] == problem_line


def test_unit_coverage_without_a_problem_prints_the_summary_and_passes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _command_line(FakeUnitCoverageChecker(_report())).run(["unit-coverage"]) == 0

    assert capsys.readouterr().out == (
        "pkg: 4 test files map to 2 of 3 modules, 1 are listed without a unit;"
        " 0 of 3 modules short of their own tests\n"
    )


def test_unit_coverage_on_a_broken_input_prints_its_error_on_one_line_and_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    broken_input = BrokenInputError("/work/packages/pkg/.coverage: no per-test branch coverage")
    command_line = _command_line(FakeUnitCoverageChecker(_report(), broken_input=broken_input))

    assert command_line.run(["unit-coverage"]) == 1

    assert capsys.readouterr() == (
        "",
        "error: /work/packages/pkg/.coverage: no per-test branch coverage\n",
    )


def test_the_bare_invocation_is_refused_with_a_usage_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    unit_coverage_checker = FakeUnitCoverageChecker(_report())

    with pytest.raises(SystemExit) as exit_info:
        _command_line(unit_coverage_checker).run([])

    assert exit_info.value.code == 2
    assert capsys.readouterr().err.startswith("usage: coverage_checks ")
    assert unit_coverage_checker.check_count == 0


def test_the_help_lists_the_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _command_line(FakeUnitCoverageChecker(_report())).run(["--help"])

    assert exit_info.value.code == 0
    assert "{unit-coverage}" in capsys.readouterr().out
