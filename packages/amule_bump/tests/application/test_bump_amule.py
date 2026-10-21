from dataclasses import dataclass, field
from pathlib import PurePath

import pytest

from amule_bump.application.bump_amule import BumpAmule
from amule_bump.domain.bump_error import BumpError
from amule_bump.domain.dockerfile import Pin
from amule_bump.domain.git_object import GitObject, GitObjectKind
from amule_bump.ports.driving.amule_bumper import (
    AmuleBump,
    PinAheadOfLatest,
    PinIsLatest,
)
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
        latest_release_tag=latest,
        tag_targets_by_tag={latest: GitObject(GitObjectKind.COMMIT, NEW_COMMIT)},
        file_texts_by_ref_and_path={
            ("3.1.0", "docs/CHANGELOG.md"): f"## Version 3.1.0 - REST\n{CHANGELOG_LINE}\n"
        },
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

    def run(
        self, repo_reader: FakeRepoReader, *, dry_run: bool
    ) -> AmuleBump | PinIsLatest | PinAheadOfLatest:
        bump_amule = BumpAmule(
            repo_reader=repo_reader,
            dockerfile_reader=self.dockerfile,
            dockerfile_writer=self.dockerfile,
            pull_request_body_writer=self.pull_request_body_writer,
            step_output_writer=self.step_output_writer,
            changelog_width_characters=30,
        )
        return bump_amule.bump_amule(DOCKERFILE_PATH, BODY_PATH, dry_run=dry_run)

    def wrote_nothing(self, dockerfile_text: str) -> bool:
        return (
            self.dockerfile.dockerfile_texts_by_path == {DOCKERFILE_PATH: dockerfile_text}
            and self.pull_request_body_writer.bodies_by_path == {}
            and self.step_output_writer.step_outputs == []
        )


def test_same_version_is_the_pin_is_latest() -> None:
    pinned = DOCKERFILE.replace("3.0.1", "3.1.0")
    bump = Bump(dockerfile=FakeDockerfile({DOCKERFILE_PATH: pinned}))
    assert bump.run(upstream("3.1.0"), dry_run=False) == PinIsLatest("3.1.0")
    assert bump.wrote_nothing(pinned)


def test_an_older_upstream_release_is_the_pin_ahead_of_latest() -> None:
    bump = Bump()
    assert bump.run(upstream("3.0.0"), dry_run=False) == PinAheadOfLatest(
        pinned_version="3.0.1", latest_version="3.0.0"
    )
    assert bump.wrote_nothing(DOCKERFILE)


def test_a_new_release_rewrites_the_pin_and_writes_the_body_it_returns() -> None:
    bump = Bump()
    amule_bump = bump.run(upstream("3.1.0"), dry_run=False)
    assert bump.dockerfile.dockerfile_texts_by_path == {
        DOCKERFILE_PATH: f"FROM debian\nARG AMULE_VERSION=3.1.0\nARG AMULE_COMMIT={NEW_COMMIT}\n"
    }
    assert amule_bump == AmuleBump(
        Pin("3.1.0", NEW_COMMIT), bump.pull_request_body_writer.bodies_by_path[BODY_PATH]
    )
    assert amule_bump.body.startswith("Bumps aMule from 3.0.1 to [3.1.0]")


def test_a_new_release_is_announced_to_the_workflow() -> None:
    bump = Bump()
    bump.run(upstream("3.1.0"), dry_run=False)
    assert bump.step_output_writer.step_outputs == [("3.1.0", BODY_PATH)]


def test_the_changelog_wraps_at_the_width_the_bump_is_given() -> None:
    amule_bump = Bump().run(upstream("3.1.0"), dry_run=False)
    assert isinstance(amule_bump, AmuleBump)
    assert "- amuleapi, word word word\nword word word word word word\nword\n" in amule_bump.body


def test_a_dry_run_returns_the_new_pin_and_body_and_writes_nothing() -> None:
    bump = Bump()
    amule_bump = bump.run(upstream("3.1.0"), dry_run=True)
    assert isinstance(amule_bump, AmuleBump)
    assert amule_bump.new_pin == Pin("3.1.0", NEW_COMMIT)
    assert amule_bump.body.startswith("Bumps aMule from 3.0.1 to [3.1.0]")
    assert bump.wrote_nothing(DOCKERFILE)


def test_a_bad_pin_raises_before_reading_upstream() -> None:
    bump = Bump(dockerfile=FakeDockerfile({DOCKERFILE_PATH: "FROM debian\n"}))
    with pytest.raises(BumpError, match="expected one 'ARG AMULE_VERSION=' line, found 0"):
        bump.run(FakeRepoReader(), dry_run=False)


def test_a_missing_dockerfile_raises_before_reading_upstream() -> None:
    bump = Bump(dockerfile=FakeDockerfile({}))
    with pytest.raises(FileNotFoundError, match=f"no Dockerfile at {DOCKERFILE_PATH}"):
        bump.run(FakeRepoReader(), dry_run=False)
