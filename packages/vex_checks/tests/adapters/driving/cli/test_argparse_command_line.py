"""The command line: one subcommand per check, which it calls with typed arguments."""

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from tests.fakes import FakeImageClaimsChecker, ImageClaimsCheck
from vex_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from vex_checks.domain.violations import Violation

_IMAGE_COMMANDS = ["image-claims", "stale-claims"]
_TREE_COMMANDS = ["source-claims", "claim-coverage"]
_SARIF_OPTIONS = pytest.mark.parametrize(
    ("options", "sarif_output"),
    [
        ([], None),
        (["--format", "sarif", "--output", "o.sarif"], Path("o.sarif")),
        (["--format", "fail", "--output", "o.sarif"], None),
    ],
    ids=["fail-by-default", "sarif-to-the-output", "output-ignored-without-sarif"],
)
_PROBLEMS = (
    Violation("CVE-A", "dpkg package 'nghttp2' is present", "security/crawler.vex.openvex.json"),
    Violation("CVE-B", "declared amule 2.1.1 is below 2.1.2", "/tmp/vex.openvex.json"),
)


class _Checks:
    """The image claims' checker, and the other checks recording each call and its arguments,
    each answering a distinct exit code."""

    def __init__(self, problems: Sequence[Violation] = ()) -> None:
        self.image_claims_checker = FakeImageClaimsChecker(problems)
        self.calls: list[tuple[str, tuple[Path | None, ...]]] = []

    def command_line(self) -> ArgparseCommandLine:
        return ArgparseCommandLine(
            image_claims_checker=self.image_claims_checker,
            check_stale_claims=self._recorder("stale-claims"),
            check_source_claims=self._recorder("source-claims"),
            check_claim_coverage=self._recorder("claim-coverage"),
        )

    def ran_none(self) -> bool:
        return self.calls == [] and self.image_claims_checker.checks == []

    def _recorder(self, command: str) -> Callable[..., int]:
        def record(*arguments: Path | None) -> int:
            self.calls.append((command, arguments))
            return 3

        return record


@_SARIF_OPTIONS
def test_image_claims_checks_the_sbom_the_resolved_vex_and_its_sarif_output(
    options: list[str], sarif_output: Path | None
) -> None:
    checks = _Checks()

    checks.command_line().run(["image-claims", "--sbom", "s.json", "--vex", "v.json", *options])

    assert checks.image_claims_checker.checks == [
        ImageClaimsCheck(Path("s.json"), Path("v.json").resolve(), sarif_output)
    ]
    assert checks.calls == []


def test_image_claims_prints_each_problem_as_an_error_and_returns_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    checks = _Checks(_PROBLEMS)

    exit_code = checks.command_line().run(["image-claims", "--sbom", "s.json", "--vex", "v.json"])

    assert exit_code == 1
    assert capsys.readouterr().out == (
        "::error::CVE-A: dpkg package 'nghttp2' is present (security/crawler.vex.openvex.json)\n"
        "::error::CVE-B: declared amule 2.1.1 is below 2.1.2 (/tmp/vex.openvex.json)\n"
    )


def test_image_claims_with_no_problem_prints_nothing_and_returns_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    checks = _Checks()

    exit_code = checks.command_line().run(["image-claims", "--sbom", "s.json", "--vex", "v.json"])

    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_image_claims_asked_for_sarif_prints_nothing_and_returns_zero_despite_problems(
    capsys: pytest.CaptureFixture[str],
) -> None:
    checks = _Checks(_PROBLEMS)

    exit_code = checks.command_line().run(
        [
            "image-claims",
            "--sbom",
            "s.json",
            "--vex",
            "v.json",
            "--format",
            "sarif",
            "--output",
            "o",
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == ""


@_SARIF_OPTIONS
def test_stale_claims_runs_over_the_sbom_the_vex_and_its_sarif_output(
    options: list[str], sarif_output: Path | None
) -> None:
    checks = _Checks()

    exit_code = checks.command_line().run(
        ["stale-claims", "--sbom", "s.json", "--vex", "v.json", *options]
    )

    assert exit_code == 3
    assert checks.calls == [("stale-claims", (Path("s.json"), Path("v.json"), sarif_output))]
    assert checks.image_claims_checker.checks == []


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
    assert checks.ran_none()


@pytest.mark.parametrize("command", _IMAGE_COMMANDS)
def test_an_image_check_requires_the_sbom_and_the_vex(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    checks = _Checks()

    with pytest.raises(SystemExit) as exit_info:
        checks.command_line().run([command])

    assert exit_info.value.code == 2
    assert "the following arguments are required: --sbom, --vex" in capsys.readouterr().err
    assert checks.ran_none()


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
    assert checks.ran_none()


def test_the_help_lists_the_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _Checks().command_line().run(["--help"])

    assert exit_info.value.code == 0
    assert "{image-claims,stale-claims,source-claims,claim-coverage}" in capsys.readouterr().out
