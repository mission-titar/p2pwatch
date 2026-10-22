"""The command line: one subcommand, which calls the bumper and prints its answer."""

from email.message import Message
from pathlib import PurePath
from urllib.error import HTTPError

import pytest

from amule_bump.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from amule_bump.application.ports.driving.amule_bumper import (
    AmuleBump,
    AmuleBumper,
    PinAheadOfLatest,
    PinIsLatest,
)
from amule_bump.domain.bump_error import BumpError
from amule_bump.domain.dockerfile import DOCKERFILE_PATH, Pin
from amule_bump.domain.pull_request_body import PULL_REQUEST_BODY_FILENAME
from tests.fakes.application.use_cases.fake_amule_bumper import FakeAmuleBumper

CWD = PurePath("/repo")
TEMPORARY_DIRECTORY = PurePath("/scratch")
NEW_PIN = Pin("3.1.0", "909d304d993ee07df6c6f6acf501a6d791d53666")


def command_line(amule_bumper: AmuleBumper) -> ArgparseCommandLine:
    return ArgparseCommandLine(
        amule_bumper=amule_bumper, cwd=CWD, temporary_directory=TEMPORARY_DIRECTORY
    )


def test_bump_passes_its_options_under_the_working_directory() -> None:
    amule_bumper = FakeAmuleBumper(PinIsLatest("3.1.0"))
    argv = ["bump", "--dockerfile", "Dockerfile", "--body-file", "/abs/body.md", "--dry-run"]

    assert command_line(amule_bumper).run(argv) == 0

    assert amule_bumper.calls == [(CWD / "Dockerfile", PurePath("/abs/body.md"), True)]


def test_bump_without_options_takes_the_domains_files_under_cwd_and_temp() -> None:
    amule_bumper = FakeAmuleBumper(PinIsLatest("3.1.0"))

    command_line(amule_bumper).run(["bump"])

    assert amule_bumper.calls == [
        (CWD / DOCKERFILE_PATH, TEMPORARY_DIRECTORY / PULL_REQUEST_BODY_FILENAME, False)
    ]


def test_the_pin_is_latest_is_nothing_to_do(capsys: pytest.CaptureFixture[str]) -> None:
    assert command_line(FakeAmuleBumper(PinIsLatest("3.1.0"))).run(["bump"]) == 0
    assert capsys.readouterr().out == "aMule 3.1.0 is the latest release: nothing to do\n"


def test_the_pin_ahead_of_latest_is_nothing_to_do(capsys: pytest.CaptureFixture[str]) -> None:
    pin_ahead = PinAheadOfLatest(pinned_version="3.0.1", latest_version="3.0.0")
    assert command_line(FakeAmuleBumper(pin_ahead)).run(["bump"]) == 0
    assert capsys.readouterr().out == (
        "latest upstream release 3.0.0 is older than the pinned 3.0.1: nothing to do\n"
    )


def test_a_dry_run_prints_the_new_pin_and_the_body(capsys: pytest.CaptureFixture[str]) -> None:
    amule_bump = AmuleBump(NEW_PIN, "Bumps aMule\n")
    assert command_line(FakeAmuleBumper(amule_bump)).run(["bump", "--dry-run"]) == 0
    assert capsys.readouterr().out == (
        "ARG AMULE_VERSION=3.1.0\n"
        f"ARG AMULE_COMMIT={NEW_PIN.commit}\n"
        "--- PR body (12 characters) ---\n"
        "Bumps aMule\n"
    )


def test_a_bump_prints_nothing_of_what_it_wrote(capsys: pytest.CaptureFixture[str]) -> None:
    amule_bump = AmuleBump(NEW_PIN, "Bumps aMule\n")
    assert command_line(FakeAmuleBumper(amule_bump)).run(["bump"]) == 0
    assert capsys.readouterr().out == ""


def test_a_bump_error_is_printed_and_fails(capsys: pytest.CaptureFixture[str]) -> None:
    bump_error = BumpError("expected one 'ARG AMULE_VERSION=' line, found 0")
    assert command_line(FakeAmuleBumper(bump_error)).run(["bump"]) == 1
    assert capsys.readouterr().err == "error: expected one 'ARG AMULE_VERSION=' line, found 0\n"


def test_an_http_failure_is_printed_and_fails(capsys: pytest.CaptureFixture[str]) -> None:
    http_error = HTTPError("releases/latest", 503, "Service Unavailable", Message(), None)
    assert command_line(FakeAmuleBumper(http_error)).run(["bump"]) == 1
    assert capsys.readouterr().err == "error: HTTP Error 503: Service Unavailable\n"


def test_the_bare_invocation_is_refused_with_a_usage_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        command_line(FakeAmuleBumper(PinIsLatest("3.1.0"))).run([])

    assert exit_info.value.code == 2
    assert capsys.readouterr().err.startswith("usage: amule_bump ")


def test_the_help_lists_the_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        command_line(FakeAmuleBumper(PinIsLatest("3.1.0"))).run(["--help"])

    assert exit_info.value.code == 0
    assert "{bump}" in capsys.readouterr().out
