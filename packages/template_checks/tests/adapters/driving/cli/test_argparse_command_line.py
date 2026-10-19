"""The command line: one subcommand per check, which it calls with the templates directory."""

from pathlib import Path

import pytest

from template_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine


class _Checks:
    """Records each check's call and its templates directory."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Path]] = []

    def command_line(self) -> ArgparseCommandLine:
        return ArgparseCommandLine(
            check_logic_free=self._check_logic_free, print_read_names=self._print_read_names
        )

    def _check_logic_free(self, templates_dir: Path) -> int:
        self.calls.append(("logic-free", templates_dir))
        return 3

    def _print_read_names(self, templates_dir: Path) -> None:
        self.calls.append(("read-names", templates_dir))


def test_logic_free_runs_its_check_over_the_directory_and_returns_its_exit_code() -> None:
    checks = _Checks()

    assert checks.command_line().run(["logic-free", "templates"]) == 3

    assert checks.calls == [("logic-free", Path("templates"))]


def test_read_names_prints_the_directory_s_names_and_exits_0() -> None:
    checks = _Checks()

    assert checks.command_line().run(["read-names", "templates"]) == 0

    assert checks.calls == [("read-names", Path("templates"))]


@pytest.mark.parametrize("command", ["logic-free", "read-names"])
def test_a_check_requires_the_templates_directory(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    checks = _Checks()

    with pytest.raises(SystemExit) as exit_info:
        checks.command_line().run([command])

    assert exit_info.value.code == 2
    assert "the following arguments are required: templates_dir" in capsys.readouterr().err
    assert checks.calls == []


def test_the_bare_invocation_is_refused_with_a_usage_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _Checks().command_line().run([])

    assert exit_info.value.code == 2
    assert capsys.readouterr().err.startswith("usage: template_checks ")


def test_the_help_lists_the_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _Checks().command_line().run(["--help"])

    assert exit_info.value.code == 0
    assert "{logic-free,read-names}" in capsys.readouterr().out
