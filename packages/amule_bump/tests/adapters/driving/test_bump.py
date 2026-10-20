from dataclasses import dataclass, field
from email.message import Message
from pathlib import PurePath
from urllib.error import HTTPError

import pytest

from amule_bump.adapters.driving.bump import main
from tests.fakes import (
    FakeDockerfile,
    FakePullRequestBodyWriter,
    FakeRepoReader,
    FakeStepOutputWriter,
)

OLD_COMMIT = "02db0d7faecfc377694ff6242bc23346185990ed"
NEW_COMMIT = "909d304d993ee07df6c6f6acf501a6d791d53666"
DOCKERFILE = f"FROM debian\nARG AMULE_VERSION=3.0.1\nARG AMULE_COMMIT={OLD_COMMIT}\n"
DOCKERFILE_PATH = PurePath("/repo/packages/amule/Dockerfile")
BODY_PATH = PurePath("/tmp/body.md")
CHANGELOG_LINE = "- amuleapi, " + "word " * 10


def upstream(latest: str) -> FakeRepoReader:
    return FakeRepoReader(
        json={
            "releases/latest": {"tag_name": latest},
            f"git/ref/tags/{latest}": {"object": {"type": "commit", "sha": NEW_COMMIT}},
        },
        files={("3.1.0", "docs/CHANGELOG.md"): f"## Version 3.1.0 - REST\n{CHANGELOG_LINE}\n"},
    )


@dataclass
class Bump:
    """The bump's driven ports, the Dockerfile at ``DOCKERFILE_PATH`` holding ``DOCKERFILE``."""

    dockerfile: FakeDockerfile = field(
        default_factory=lambda: FakeDockerfile({DOCKERFILE_PATH: DOCKERFILE})
    )
    pull_request_body_writer: FakePullRequestBodyWriter = field(
        default_factory=FakePullRequestBodyWriter
    )
    step_output_writer: FakeStepOutputWriter = field(default_factory=FakeStepOutputWriter)

    def run(self, repo_reader: FakeRepoReader, *, dry_run: bool) -> int:
        return main(
            DOCKERFILE_PATH,
            BODY_PATH,
            dry_run,
            repo_reader=repo_reader,
            dockerfile_reader=self.dockerfile,
            dockerfile_writer=self.dockerfile,
            pull_request_body_writer=self.pull_request_body_writer,
            step_output_writer=self.step_output_writer,
            changelog_width_characters=30,
        )

    def wrote_nothing(self, dockerfile_text: str) -> bool:
        return (
            self.dockerfile.dockerfile_texts_by_path == {DOCKERFILE_PATH: dockerfile_text}
            and self.pull_request_body_writer.bodies_by_path == {}
            and self.step_output_writer.step_outputs == []
        )


def test_same_version_is_nothing_to_do(capsys: pytest.CaptureFixture[str]) -> None:
    pinned = DOCKERFILE.replace("3.0.1", "3.1.0")
    bump = Bump(dockerfile=FakeDockerfile({DOCKERFILE_PATH: pinned}))
    assert bump.run(upstream("3.1.0"), dry_run=False) == 0
    assert capsys.readouterr().out == "aMule 3.1.0 is the latest release: nothing to do\n"
    assert bump.wrote_nothing(pinned)


def test_an_older_upstream_release_is_nothing_to_do(capsys: pytest.CaptureFixture[str]) -> None:
    bump = Bump()
    assert bump.run(upstream("3.0.0"), dry_run=False) == 0
    assert capsys.readouterr().out == (
        "latest upstream release 3.0.0 is older than the pinned 3.0.1: nothing to do\n"
    )
    assert bump.wrote_nothing(DOCKERFILE)


def test_a_new_release_rewrites_the_pin_and_writes_the_body() -> None:
    bump = Bump()
    assert bump.run(upstream("3.1.0"), dry_run=False) == 0
    assert bump.dockerfile.dockerfile_texts_by_path == {
        DOCKERFILE_PATH: f"FROM debian\nARG AMULE_VERSION=3.1.0\nARG AMULE_COMMIT={NEW_COMMIT}\n"
    }
    body = bump.pull_request_body_writer.bodies_by_path[BODY_PATH]
    assert body.startswith("Bumps aMule from 3.0.1 to [3.1.0]")
    assert "- amuleapi" in body


def test_a_new_release_is_announced_to_the_workflow() -> None:
    bump = Bump()
    bump.run(upstream("3.1.0"), dry_run=False)
    assert bump.step_output_writer.step_outputs == [("3.1.0", BODY_PATH)]


def test_the_changelog_wraps_at_the_width_the_bump_is_given() -> None:
    bump = Bump()
    bump.run(upstream("3.1.0"), dry_run=False)
    body = bump.pull_request_body_writer.bodies_by_path[BODY_PATH]
    assert "- amuleapi, word word word\nword word word word word word\nword\n" in body


def test_dry_run_prints_the_new_pin_and_body_and_writes_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    bump = Bump()
    assert bump.run(upstream("3.1.0"), dry_run=True) == 0
    printed = capsys.readouterr().out
    assert printed.startswith(
        f"ARG AMULE_VERSION=3.1.0\nARG AMULE_COMMIT={NEW_COMMIT}\n--- PR body ("
    )
    assert "Bumps aMule from 3.0.1 to [3.1.0]" in printed
    assert bump.wrote_nothing(DOCKERFILE)


def test_a_bad_pin_fails_with_a_clear_message(capsys: pytest.CaptureFixture[str]) -> None:
    bump = Bump(dockerfile=FakeDockerfile({DOCKERFILE_PATH: "FROM debian\n"}))
    assert bump.run(upstream("3.1.0"), dry_run=False) == 1
    assert capsys.readouterr().err == "error: expected one 'ARG AMULE_VERSION=' line, found 0\n"


def test_a_missing_dockerfile_fails_with_a_clear_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    bump = Bump(dockerfile=FakeDockerfile({}))
    assert bump.run(upstream("3.1.0"), dry_run=False) == 1
    assert capsys.readouterr().err == f"error: no Dockerfile at {DOCKERFILE_PATH}\n"


def test_an_http_failure_fails_with_a_clear_message(capsys: pytest.CaptureFixture[str]) -> None:
    class DownRepoReader(FakeRepoReader):
        def json(self, path: str) -> object:
            raise HTTPError(path, 503, "Service Unavailable", Message(), None)

    assert Bump().run(DownRepoReader(), dry_run=False) == 1
    assert capsys.readouterr().err == "error: HTTP Error 503: Service Unavailable\n"
