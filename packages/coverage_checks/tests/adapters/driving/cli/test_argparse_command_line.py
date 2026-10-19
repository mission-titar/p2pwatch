"""The command line: one subcommand, which runs the check in the package's directory."""

import pytest

from coverage_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine


def test_unit_coverage_runs_its_check_and_returns_its_exit_code() -> None:
    calls: list[str] = []

    def check_unit_coverage() -> int:
        calls.append("unit-coverage")
        return 3

    command_line = ArgparseCommandLine(check_unit_coverage=check_unit_coverage)

    assert command_line.run(["unit-coverage"]) == 3
    assert calls == ["unit-coverage"]


def test_the_bare_invocation_is_refused_with_a_usage_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        ArgparseCommandLine(check_unit_coverage=lambda: 0).run([])

    assert exit_info.value.code == 2
    assert capsys.readouterr().err.startswith("usage: coverage_checks ")


def test_the_help_lists_the_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        ArgparseCommandLine(check_unit_coverage=lambda: 0).run(["--help"])

    assert exit_info.value.code == 0
    assert "{unit-coverage}" in capsys.readouterr().out
