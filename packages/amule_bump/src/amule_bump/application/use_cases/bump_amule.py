"""Bumps aMule's pin to upstream's latest release, writing the pin and the pull request body."""

from pathlib import PurePath

from amule_bump.application.ports.driven.bump_announcer import BumpAnnouncer
from amule_bump.application.ports.driven.dockerfile_reader import DockerfileReader
from amule_bump.application.ports.driven.dockerfile_writer import DockerfileWriter
from amule_bump.application.ports.driven.pull_request_drafter import PullRequestDrafter
from amule_bump.application.ports.driven.upstream_client import UpstreamClient
from amule_bump.application.ports.driving.amule_bumper import (
    AmuleBump,
    AmuleBumper,
    PinAheadOfLatest,
    PinIsLatest,
)
from amule_bump.domain.dockerfile import Pin, read_pin, rewrite_pin
from amule_bump.domain.git_object import GitObjectKind, tagged_commit_id
from amule_bump.domain.pull_request_body import (
    CHANGELOG_PATH,
    WATCHED_FILES,
    WatchedFile,
    build_pull_request_body,
)
from amule_bump.domain.version import check_release_tag, is_newer


class BumpAmule(AmuleBumper):
    """Reads the pin and upstream's latest release; writes only when that release is newer."""

    def __init__(
        self,
        *,
        upstream_client: UpstreamClient,
        dockerfile_reader: DockerfileReader,
        dockerfile_writer: DockerfileWriter,
        pull_request_drafter: PullRequestDrafter,
        bump_announcer: BumpAnnouncer,
        changelog_width_characters: int,
    ) -> None:
        self._upstream_client = upstream_client
        self._dockerfile_reader = dockerfile_reader
        self._dockerfile_writer = dockerfile_writer
        self._pull_request_drafter = pull_request_drafter
        self._bump_announcer = bump_announcer
        self._changelog_width_characters = changelog_width_characters

    def bump_amule(
        self, dockerfile_path: PurePath, body_path: PurePath, *, dry_run: bool
    ) -> AmuleBump | PinIsLatest | PinAheadOfLatest:
        dockerfile_text = self._dockerfile_reader.read_dockerfile(dockerfile_path)
        old = read_pin(dockerfile_text)
        latest = self._upstream_client.read_latest_release_tag()
        check_release_tag(latest)
        if latest == old.version:
            return PinIsLatest(old.version)
        if not is_newer(latest, old.version):
            return PinAheadOfLatest(pinned_version=old.version, latest_version=latest)

        new = Pin(latest, self._peeled_commit(latest))
        body = build_pull_request_body(
            old,
            new,
            self._upstream_client.read_file(new.version, CHANGELOG_PATH),
            [self._watched_file(old, new, path) for path in WATCHED_FILES],
            self._changelog_width_characters,
        )
        if not dry_run:
            self._dockerfile_writer.set_dockerfile(
                dockerfile_path, rewrite_pin(dockerfile_text, new)
            )
            self._pull_request_drafter.draft_pull_request_body(body_path, body)
            self._bump_announcer.announce_bump(new.version, body_path)
        return AmuleBump(new, body)

    def _peeled_commit(self, tag: str) -> str:
        """The tag's commit, never its annotated tag object: BuildKit's --checksum wants it."""
        git_object = self._upstream_client.read_tag_target(tag)
        while git_object.kind == GitObjectKind.TAG:
            git_object = self._upstream_client.read_annotated_tag_target(git_object.object_id)
        return tagged_commit_id(tag, git_object)

    def _watched_file(self, old: Pin, new: Pin, path: str) -> WatchedFile:
        return WatchedFile(
            path,
            old_text=self._upstream_client.read_file(old.version, path),
            new_text=self._upstream_client.read_file(new.version, path),
        )
