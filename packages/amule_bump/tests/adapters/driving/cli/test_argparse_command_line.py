"""The command line: one subcommand, which it calls with the bump's options."""

import tempfile
from pathlib import Path

import pytest

from amule_bump.adapters.driving.cli.argparse_command_line import ArgparseCommandLine


class _Bump:
    """Records each call's options, returns a set exit code."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, Path, bool]] = []

    def command_line(self) -> ArgparseCommandLine:
        return ArgparseCommandLine(bump_pin=self._bump_pin)

    def _bump_pin(self, dockerfile: Path, body_file: Path, dry_run: bool) -> int:
        self.calls.append((dockerfile, body_file, dry_run))
        return 3


def test_bump_passes_its_options_and_returns_the_bump_s_exit_code() -> None:
    bump = _Bump()
    argv = ["bump", "--dockerfile", "Dockerfile", "--body-file", "body.md", "--dry-run"]

    assert bump.command_line().run(argv) == 3

    assert bump.calls == [(Path("Dockerfile"), Path("body.md"), True)]


def test_bump_without_options_bumps_the_amule_image_and_writes_the_body_to_temp() -> None:
    bump = _Bump()

    bump.command_line().run(["bump"])

    body_file = Path(tempfile.gettempdir()) / "amule-bump-pr-body.md"
    assert bump.calls == [(Path("packages/amule/Dockerfile"), body_file, False)]


def test_the_bare_invocation_is_refused_with_a_usage_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _Bump().command_line().run([])

    assert exit_info.value.code == 2
    assert capsys.readouterr().err.startswith("usage: amule_bump ")


def test_the_help_lists_the_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _Bump().command_line().run(["--help"])

    assert exit_info.value.code == 0
    assert "{bump}" in capsys.readouterr().out
