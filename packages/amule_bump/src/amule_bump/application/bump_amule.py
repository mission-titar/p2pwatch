"""Bumps aMule's pin to upstream's latest release, writing the pin and the pull request body."""

from pathlib import PurePath

from amule_bump.application.body import build_pull_request_body
from amule_bump.application.release import is_newer, latest_release_tag, peeled_commit
from amule_bump.domain.dockerfile import Pin, read_pin, rewrite_pin
from amule_bump.ports.driven.dockerfile_reader import DockerfileReader
from amule_bump.ports.driven.dockerfile_writer import DockerfileWriter
from amule_bump.ports.driven.pull_request_body_writer import PullRequestBodyWriter
from amule_bump.ports.driven.repo_reader import RepoReader
from amule_bump.ports.driven.step_output_writer import StepOutputWriter
from amule_bump.ports.driving.amule_bumper import (
    AmuleBump,
    AmuleBumper,
    PinAheadOfLatest,
    PinIsLatest,
)


class BumpAmule(AmuleBumper):
    """Reads the pin and upstream's latest release; writes only when that release is newer."""

    def __init__(
        self,
        *,
        repo_reader: RepoReader,
        dockerfile_reader: DockerfileReader,
        dockerfile_writer: DockerfileWriter,
        pull_request_body_writer: PullRequestBodyWriter,
        step_output_writer: StepOutputWriter,
        changelog_width_characters: int,
    ) -> None:
        self._repo_reader = repo_reader
        self._dockerfile_reader = dockerfile_reader
        self._dockerfile_writer = dockerfile_writer
        self._pull_request_body_writer = pull_request_body_writer
        self._step_output_writer = step_output_writer
        self._changelog_width_characters = changelog_width_characters

    def bump_amule(
        self, dockerfile_path: PurePath, body_path: PurePath, *, dry_run: bool
    ) -> AmuleBump | PinIsLatest | PinAheadOfLatest:
        dockerfile_text = self._dockerfile_reader.read_dockerfile(dockerfile_path)
        old = read_pin(dockerfile_text)
        latest = latest_release_tag(self._repo_reader)
        if latest == old.version:
            return PinIsLatest(old.version)
        if not is_newer(latest, old.version):
            return PinAheadOfLatest(pinned_version=old.version, latest_version=latest)

        new = Pin(latest, peeled_commit(self._repo_reader, latest))
        body = build_pull_request_body(
            self._repo_reader, old, new, self._changelog_width_characters
        )
        if not dry_run:
            self._dockerfile_writer.write_dockerfile(
                dockerfile_path, rewrite_pin(dockerfile_text, new)
            )
            self._pull_request_body_writer.write_pull_request_body(body_path, body)
            self._step_output_writer.write_step_outputs(new.version, body_path)
        return AmuleBump(new, body)
