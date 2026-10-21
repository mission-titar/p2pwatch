"""The command line: one subcommand, which prints the unit coverage report of the package."""

from pathlib import Path

import pytest

from coverage_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from coverage_checks.ports.driving.unit_coverage_checker import (
    NoPerTestCoverage,
    UnitCoverageReport,
)
from tests.fakes import FakeUnitCoverageChecker

_DATA_FILE = Path("/work/packages/pkg/.coverage")


def _report(*problems: str) -> UnitCoverageReport:
    return UnitCoverageReport(
        problems=problems,
        module_count=3,
        tested_module_count=2,
        mapped_test_count=4,
        listed_test_count=1,
        short_module_count=len(problems),
    )


def _command_line(unit_coverage_checker: FakeUnitCoverageChecker) -> ArgparseCommandLine:
    return ArgparseCommandLine(
        unit_coverage_checker=unit_coverage_checker, package_name="pkg", data_file=_DATA_FILE
    )


def test_unit_coverage_prints_each_problem_then_the_package_s_summary_and_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    unit_coverage_checker = FakeUnitCoverageChecker(_report("problem one", "problem two"))

    assert _command_line(unit_coverage_checker).run(["unit-coverage"]) == 1

    assert capsys.readouterr().out == (
        "problem one\n"
        "problem two\n"
        "pkg: 4 test files map to 2 of 3 modules, 1 are listed without a unit;"
        " 2 of 3 modules short of their own tests\n"
    )
    assert unit_coverage_checker.check_count == 1


def test_unit_coverage_without_a_problem_prints_the_summary_and_passes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _command_line(FakeUnitCoverageChecker(_report())).run(["unit-coverage"]) == 0

    assert capsys.readouterr().out == (
        "pkg: 4 test files map to 2 of 3 modules, 1 are listed without a unit;"
        " 0 of 3 modules short of their own tests\n"
    )


def test_unit_coverage_without_per_test_coverage_says_how_to_record_it_and_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    command_line = _command_line(FakeUnitCoverageChecker(NoPerTestCoverage()))

    assert command_line.run(["unit-coverage"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "no per-test branch coverage in /work/packages/pkg/.coverage: run this package's pytest"
        " first, with branch coverage and --cov-context=test\n"
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
