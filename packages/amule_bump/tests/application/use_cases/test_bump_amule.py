from dataclasses import dataclass, field
from pathlib import PurePath

import pytest

from amule_bump.application.ports.driving.amule_bumper import (
    AmuleBump,
    PinAheadOfLatest,
    PinIsLatest,
)
from amule_bump.application.use_cases.bump_amule import BumpAmule
from amule_bump.domain.bump_error import BumpError
from amule_bump.domain.dockerfile import Pin
from amule_bump.domain.git_object import GitObject, GitObjectKind
from tests.fakes.adapters.driven.fake_bump_announcer import FakeBumpAnnouncer
from tests.fakes.adapters.driven.fake_dockerfile_store import FakeDockerfileStore
from tests.fakes.adapters.driven.fake_pull_request_drafter import FakePullRequestDrafter
from tests.fakes.adapters.driven.fake_upstream_client import FakeUpstreamClient

OLD_COMMIT = "02db0d7faecfc377694ff6242bc23346185990ed"
NEW_COMMIT = "909d304d993ee07df6c6f6acf501a6d791d53666"
TAG_OBJECT = "6ccbfdf785390c25c8b01652684f5b06fb18e034"
NEW_COMMIT_OBJECT = GitObject(GitObjectKind.COMMIT, NEW_COMMIT)
DOCKERFILE = f"FROM debian\nARG AMULE_VERSION=3.0.1\nARG AMULE_COMMIT={OLD_COMMIT}\n"
DOCKERFILE_PATH = PurePath("/repo/packages/amule/Dockerfile")
BODY_PATH = PurePath("/tmp/body.md")
CHANGELOG_LINE = "- amuleapi, " + "word " * 10


def upstream(
    latest: str,
    *,
    tag_target: GitObject = NEW_COMMIT_OBJECT,
    annotated_tag_targets_by_object_id: dict[str, GitObject] | None = None,
    watched_texts_by_ref_and_path: dict[tuple[str, str], str] | None = None,
) -> FakeUpstreamClient:
    return FakeUpstreamClient(
        latest_release_tag=latest,
        tag_targets_by_tag={latest: tag_target},
        annotated_tag_targets_by_object_id=annotated_tag_targets_by_object_id,
        file_texts_by_ref_and_path={
            ("3.1.0", "docs/CHANGELOG.md"): f"## Version 3.1.0 - REST\n{CHANGELOG_LINE}\n",
            **(watched_texts_by_ref_and_path or {}),
        },
    )


@dataclass
class Bump:
    """The bump's driven ports, the Dockerfile at ``DOCKERFILE_PATH`` holding ``DOCKERFILE``."""

    dockerfile: FakeDockerfileStore = field(
        default_factory=lambda: FakeDockerfileStore({DOCKERFILE_PATH: DOCKERFILE})
    )
    pull_request_drafter: FakePullRequestDrafter = field(default_factory=FakePullRequestDrafter)
    bump_announcer: FakeBumpAnnouncer = field(default_factory=FakeBumpAnnouncer)

    def run(
        self, upstream_client: FakeUpstreamClient, *, dry_run: bool
    ) -> AmuleBump | PinIsLatest | PinAheadOfLatest:
        bump_amule = BumpAmule(
            upstream_client=upstream_client,
            dockerfile_reader=self.dockerfile,
            dockerfile_writer=self.dockerfile,
            pull_request_drafter=self.pull_request_drafter,
            bump_announcer=self.bump_announcer,
            changelog_width_characters=30,
        )
        return bump_amule.bump_amule(DOCKERFILE_PATH, BODY_PATH, dry_run=dry_run)

    def wrote_nothing(self, dockerfile_text: str) -> bool:
        return (
            self.dockerfile.dockerfile_texts_by_path == {DOCKERFILE_PATH: dockerfile_text}
            and self.pull_request_drafter.bodies_by_path == {}
            and self.bump_announcer.step_outputs == []
        )


def test_same_version_is_the_pin_is_latest() -> None:
    pinned = DOCKERFILE.replace("3.0.1", "3.1.0")
    bump = Bump(dockerfile=FakeDockerfileStore({DOCKERFILE_PATH: pinned}))
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
        Pin("3.1.0", NEW_COMMIT), bump.pull_request_drafter.bodies_by_path[BODY_PATH]
    )
    assert amule_bump.body.startswith("Bumps aMule from 3.0.1 to [3.1.0]")


def test_a_new_release_is_announced_to_the_workflow() -> None:
    bump = Bump()
    bump.run(upstream("3.1.0"), dry_run=False)
    assert bump.bump_announcer.step_outputs == [("3.1.0", BODY_PATH)]


def test_the_changelog_wraps_at_the_width_the_bump_is_given() -> None:
    amule_bump = Bump().run(upstream("3.1.0"), dry_run=False)
    assert isinstance(amule_bump, AmuleBump)
    assert "- amuleapi, word word word\nword word word word word word\nword\n" in amule_bump.body


def test_the_body_carries_each_watched_file_s_diff_between_the_two_tags() -> None:
    upstream_client = upstream(
        "3.1.0",
        watched_texts_by_ref_and_path={
            ("3.0.1", "cmake/options.cmake"): "option(A)\n",
            ("3.1.0", "cmake/options.cmake"): "option(B)\n",
        },
    )
    amule_bump = Bump().run(upstream_client, dry_run=True)
    assert isinstance(amule_bump, AmuleBump)
    assert "-option(A)\n+option(B)\n" in amule_bump.body


def test_an_annotated_tag_is_peeled_to_its_commit() -> None:
    upstream_client = upstream(
        "3.1.0",
        tag_target=GitObject(GitObjectKind.TAG, TAG_OBJECT),
        annotated_tag_targets_by_object_id={
            TAG_OBJECT: GitObject(GitObjectKind.COMMIT, NEW_COMMIT)
        },
    )
    amule_bump = Bump().run(upstream_client, dry_run=True)
    assert isinstance(amule_bump, AmuleBump)
    assert amule_bump.new_pin == Pin("3.1.0", NEW_COMMIT)


def test_a_tag_naming_no_commit_raises_and_writes_nothing() -> None:
    upstream_client = upstream("3.1.0", tag_target=GitObject(GitObjectKind.TREE, NEW_COMMIT))
    bump = Bump()
    with pytest.raises(BumpError, match="tag 3.1.0 points at a tree, not a commit"):
        bump.run(upstream_client, dry_run=False)
    assert bump.wrote_nothing(DOCKERFILE)


def test_a_release_tag_that_is_not_a_plain_version_raises_and_writes_nothing() -> None:
    bump = Bump()
    with pytest.raises(BumpError, match="unexpected upstream release tag 'v3.1.0'"):
        bump.run(upstream("v3.1.0"), dry_run=False)
    assert bump.wrote_nothing(DOCKERFILE)


def test_a_dry_run_returns_the_new_pin_and_body_and_writes_nothing() -> None:
    bump = Bump()
    amule_bump = bump.run(upstream("3.1.0"), dry_run=True)
    assert isinstance(amule_bump, AmuleBump)
    assert amule_bump.new_pin == Pin("3.1.0", NEW_COMMIT)
    assert amule_bump.body.startswith("Bumps aMule from 3.0.1 to [3.1.0]")
    assert bump.wrote_nothing(DOCKERFILE)


def test_a_bad_pin_raises_before_reading_upstream() -> None:
    bump = Bump(dockerfile=FakeDockerfileStore({DOCKERFILE_PATH: "FROM debian\n"}))
    with pytest.raises(BumpError, match="expected one 'ARG AMULE_VERSION=' line, found 0"):
        bump.run(FakeUpstreamClient(), dry_run=False)


def test_a_missing_dockerfile_raises_before_reading_upstream() -> None:
    bump = Bump(dockerfile=FakeDockerfileStore({}))
    with pytest.raises(FileNotFoundError, match=f"no Dockerfile at {DOCKERFILE_PATH}"):
        bump.run(FakeUpstreamClient(), dry_run=False)
