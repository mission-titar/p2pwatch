"""The command line: one subcommand per check, which it calls with typed arguments."""

from collections.abc import Sequence
from pathlib import PurePath

import pytest

from tests.fakes.application.use_cases.fake_applied_claims_checker import (
    AppliedClaimsCheck,
    FakeAppliedClaimsChecker,
)
from tests.fakes.application.use_cases.fake_claim_coverage_checker import FakeClaimCoverageChecker
from tests.fakes.application.use_cases.fake_image_claims_checker import (
    FakeImageClaimsChecker,
    ImageClaimsCheck,
)
from vex_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from vex_checks.domain.broken_input_error import BrokenInputError
from vex_checks.domain.claim_problem import ClaimProblem

_CWD = PurePath("/work/repo")
_IMAGE_COMMANDS = ["image-claims", "applied-claims"]
_SARIF_OPTIONS = pytest.mark.parametrize(
    ("options", "sarif_output"),
    [([], None), (["--sarif", "o.sarif"], _CWD / "o.sarif")],
    ids=["printed-by-default", "sarif-to-its-path"],
)
_PROBLEMS = (
    ClaimProblem("CVE-A", "dpkg package 'nghttp2' is present"),
    ClaimProblem("CVE-B", "declared amule 2.1.1 is below 2.1.2"),
)
_VEX_LOCATION = "security/crawler.vex.openvex.json"


class _Checks:
    """The two image checkers, answering the same report, and the claim coverage checker."""

    def __init__(
        self,
        problems: Sequence[ClaimProblem] = (),
        claim_coverage_problems: Sequence[ClaimProblem] = (),
    ) -> None:
        self.image_claims_checker = FakeImageClaimsChecker(problems, _VEX_LOCATION)
        self.applied_claims_checker = FakeAppliedClaimsChecker(problems, _VEX_LOCATION)
        self.claim_coverage_checker = FakeClaimCoverageChecker(claim_coverage_problems)

    def command_line(self) -> ArgparseCommandLine:
        return ArgparseCommandLine(
            image_claims_checker=self.image_claims_checker,
            applied_claims_checker=self.applied_claims_checker,
            claim_coverage_checker=self.claim_coverage_checker,
            cwd=_CWD,
        )

    def ran_none(self) -> bool:
        return (
            self.image_claims_checker.checks == []
            and self.applied_claims_checker.checks == []
            and self.claim_coverage_checker.check_count == 0
        )


@_SARIF_OPTIONS
def test_image_claims_checks_the_sbom_the_vex_and_its_sarif_output_under_the_cwd(
    options: list[str], sarif_output: PurePath | None
) -> None:
    checks = _Checks()

    checks.command_line().run(["image-claims", "--sbom", "s.json", "--vex", "v.json", *options])

    assert checks.image_claims_checker.checks == [
        ImageClaimsCheck(_CWD / "s.json", _CWD / "v.json", sarif_output)
    ]
    assert checks.applied_claims_checker.checks == []


@pytest.mark.parametrize(
    ("vex", "vex_path"),
    [
        ("../security/v.json", PurePath("/work/repo/../security/v.json")),
        ("/tmp/v.json", PurePath("/tmp/v.json")),
    ],
    ids=["relative-under-the-cwd-unresolved", "absolute-as-given"],
)
def test_an_image_check_is_given_the_vex_under_the_cwd_as_written(
    vex: str, vex_path: PurePath
) -> None:
    checks = _Checks()

    checks.command_line().run(["image-claims", "--sbom", "/s.json", "--vex", vex])
    checks.command_line().run(["applied-claims", "--sbom", "/s.json", "--vex", vex])

    sbom_path = PurePath("/s.json")
    assert checks.image_claims_checker.checks == [ImageClaimsCheck(sbom_path, vex_path, None)]
    assert checks.applied_claims_checker.checks == [AppliedClaimsCheck(sbom_path, vex_path, None)]


@pytest.mark.parametrize("command", _IMAGE_COMMANDS)
def test_an_image_check_prints_each_problem_as_an_error_and_returns_one(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    checks = _Checks(_PROBLEMS)

    exit_code = checks.command_line().run([command, "--sbom", "s.json", "--vex", "v.json"])

    assert exit_code == 1
    assert capsys.readouterr().out == (
        "::error::CVE-A: dpkg package 'nghttp2' is present (security/crawler.vex.openvex.json)\n"
        "::error::CVE-B: declared amule 2.1.1 is below 2.1.2 (security/crawler.vex.openvex.json)\n"
    )


@pytest.mark.parametrize("command", _IMAGE_COMMANDS)
def test_an_image_check_with_no_problem_prints_nothing_and_returns_zero(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    checks = _Checks()

    exit_code = checks.command_line().run([command, "--sbom", "s.json", "--vex", "v.json"])

    assert exit_code == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("command", _IMAGE_COMMANDS)
def test_an_image_check_asked_for_sarif_prints_nothing_and_returns_zero_despite_problems(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    checks = _Checks(_PROBLEMS)

    exit_code = checks.command_line().run(
        [command, "--sbom", "s.json", "--vex", "v.json", "--sarif", "o"]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == ""


@_SARIF_OPTIONS
def test_applied_claims_checks_the_sbom_the_vex_and_its_sarif_output_under_the_cwd(
    options: list[str], sarif_output: PurePath | None
) -> None:
    checks = _Checks()

    checks.command_line().run(["applied-claims", "--sbom", "s.json", "--vex", "v.json", *options])

    assert checks.applied_claims_checker.checks == [
        AppliedClaimsCheck(_CWD / "s.json", _CWD / "v.json", sarif_output)
    ]
    assert checks.image_claims_checker.checks == []


@pytest.mark.parametrize("command", _IMAGE_COMMANDS)
@pytest.mark.parametrize("option", ["--format", "--output"])
def test_an_image_check_refuses_the_former_format_and_output_options(
    command: str, option: str, capsys: pytest.CaptureFixture[str]
) -> None:
    checks = _Checks()

    with pytest.raises(SystemExit) as exit_info:
        checks.command_line().run([command, "--sbom", "s.json", "--vex", "v.json", option, "o"])

    assert exit_info.value.code == 2
    assert f"unrecognized arguments: {option} o" in capsys.readouterr().err
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


def test_claim_coverage_prints_each_problem_as_an_error_and_returns_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    checks = _Checks(
        claim_coverage_problems=[
            ClaimProblem("CVE-A", "claim has no premise or source rule"),
            ClaimProblem("CVE-B", "premise has no claim"),
        ]
    )

    assert checks.command_line().run(["claim-coverage"]) == 1

    assert capsys.readouterr().out == (
        "::error::CVE-A: claim has no premise or source rule\n"
        "::error::CVE-B: premise has no claim\n"
    )
    assert checks.claim_coverage_checker.check_count == 1
    assert checks.image_claims_checker.checks == []
    assert checks.applied_claims_checker.checks == []


def test_claim_coverage_with_no_problem_prints_nothing_and_returns_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    checks = _Checks()

    assert checks.command_line().run(["claim-coverage"]) == 0

    assert capsys.readouterr().out == ""
    assert checks.claim_coverage_checker.check_count == 1


def test_a_broken_input_is_printed_as_one_error_line_and_returns_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    checks = _Checks()
    checks.claim_coverage_checker = FakeClaimCoverageChecker(
        broken_input_error=BrokenInputError("/work/repo/security/crawler.vex.json: no such file")
    )

    assert checks.command_line().run(["claim-coverage"]) == 1

    captured = capsys.readouterr()
    assert captured.err == "error: /work/repo/security/crawler.vex.json: no such file\n"
    assert captured.out == ""


@pytest.mark.parametrize("command", ["source-claims", "stale-claims"])
def test_a_former_check_is_no_subcommand(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    checks = _Checks()

    with pytest.raises(SystemExit) as exit_info:
        checks.command_line().run([command])

    assert exit_info.value.code == 2
    assert f"invalid choice: '{command}'" in capsys.readouterr().err
    assert checks.ran_none()


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
    assert "{image-claims,applied-claims,claim-coverage}" in capsys.readouterr().out
