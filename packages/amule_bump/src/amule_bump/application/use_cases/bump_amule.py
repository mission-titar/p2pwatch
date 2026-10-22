"""Bumps aMule's pin to upstream's latest release, writing the pin and the pull request body."""

from pathlib import PurePath

from amule_bump.application.ports.driven.dockerfile_reader import DockerfileReader
from amule_bump.application.ports.driven.dockerfile_writer import DockerfileWriter
from amule_bump.application.ports.driven.pull_request_body_writer import PullRequestDrafter
from amule_bump.application.ports.driven.repo_reader import UpstreamClient
from amule_bump.application.ports.driven.step_output_writer import BumpAnnouncer
from amule_bump.application.ports.driving.amule_bumper import (
    AmuleBump,
    AmuleBumper,
    PinAheadOfLatest,
    PinIsLatest,
)
from amule_bump.application.use_cases.body import build_pull_request_body
from amule_bump.application.use_cases.release import is_newer, latest_release_tag, peeled_commit
from amule_bump.domain.dockerfile import Pin, read_pin, rewrite_pin


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
        latest = latest_release_tag(self._upstream_client)
        if latest == old.version:
            return PinIsLatest(old.version)
        if not is_newer(latest, old.version):
            return PinAheadOfLatest(pinned_version=old.version, latest_version=latest)

        new = Pin(latest, peeled_commit(self._upstream_client, latest))
        body = build_pull_request_body(
            self._upstream_client, old, new, self._changelog_width_characters
        )
        if not dry_run:
            self._dockerfile_writer.set_dockerfile(
                dockerfile_path, rewrite_pin(dockerfile_text, new)
            )
            self._pull_request_drafter.draft_pull_request_body(body_path, body)
            self._bump_announcer.announce_bump(new.version, body_path)
        return AmuleBump(new, body)
