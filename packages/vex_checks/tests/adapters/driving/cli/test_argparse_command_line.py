"""The command line: one subcommand per check, which it calls with typed arguments."""

from collections.abc import Callable
from pathlib import Path

import pytest

from vex_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine

_IMAGE_COMMANDS = ["image-claims", "stale-claims"]
_TREE_COMMANDS = ["source-claims", "claim-coverage"]


class _Checks:
    """Records each check's call and its arguments, and answers a distinct exit code."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Path | None, ...]]] = []

    def command_line(self) -> ArgparseCommandLine:
        return ArgparseCommandLine(
            check_image_claims=self._recorder("image-claims"),
            check_stale_claims=self._recorder("stale-claims"),
            check_source_claims=self._recorder("source-claims"),
            check_claim_coverage=self._recorder("claim-coverage"),
        )

    def _recorder(self, command: str) -> Callable[..., int]:
        def record(*arguments: Path | None) -> int:
            self.calls.append((command, arguments))
            return 3

        return record


@pytest.mark.parametrize("command", _IMAGE_COMMANDS)
@pytest.mark.parametrize(
    ("options", "sarif_output"),
    [
        ([], None),
        (["--format", "sarif", "--output", "o.sarif"], Path("o.sarif")),
        (["--format", "fail", "--output", "o.sarif"], None),
    ],
    ids=["fail-by-default", "sarif-to-the-output", "output-ignored-without-sarif"],
)
def test_an_image_check_runs_over_the_sbom_the_vex_and_its_sarif_output(
    command: str, options: list[str], sarif_output: Path | None
) -> None:
    checks = _Checks()

    exit_code = checks.command_line().run(
        [command, "--sbom", "s.json", "--vex", "v.json", *options]
    )

    assert exit_code == 3
    assert checks.calls == [(command, (Path("s.json"), Path("v.json"), sarif_output))]


@pytest.mark.parametrize("command", _IMAGE_COMMANDS)
def test_the_sarif_format_without_an_output_exits_2_with_the_subcommand_usage(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    checks = _Checks()

    with pytest.raises(SystemExit) as exit_info:
        checks.command_line().run(
            [command, "--sbom", "s.json", "--vex", "v.json", "--format", "sarif"]
        )

    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert err.startswith(f"usage: vex_checks {command} ")
    assert "--output is required with --format sarif" in err
    assert checks.calls == []


@pytest.mark.parametrize("command", _IMAGE_COMMANDS)
def test_an_image_check_requires_the_sbom_and_the_vex(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    checks = _Checks()

    with pytest.raises(SystemExit) as exit_info:
        checks.command_line().run([command])

    assert exit_info.value.code == 2
    assert "the following arguments are required: --sbom, --vex" in capsys.readouterr().err
    assert checks.calls == []


@pytest.mark.parametrize("command", _TREE_COMMANDS)
def test_a_tree_check_runs_alone_and_returns_its_exit_code(command: str) -> None:
    checks = _Checks()

    assert checks.command_line().run([command]) == 3

    assert checks.calls == [(command, ())]


def test_the_bare_invocation_is_refused_with_a_usage_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    checks = _Checks()

    with pytest.raises(SystemExit) as exit_info:
        checks.command_line().run([])

    assert exit_info.value.code == 2
    assert capsys.readouterr().err.startswith("usage: vex_checks ")
    assert checks.calls == []


def test_the_help_lists_the_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _Checks().command_line().run(["--help"])

    assert exit_info.value.code == 0
    assert "{image-claims,stale-claims,source-claims,claim-coverage}" in capsys.readouterr().out
