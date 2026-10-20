"""Bump aMule's Dockerfile pin to the latest upstream release and write the PR body.

The workflow opens the PR afterwards, from the `version` and `body-path` step outputs.
"""

import sys
from pathlib import PurePath

from amule_bump.application.body import build_pull_request_body
from amule_bump.application.release import is_newer, latest_release_tag, peeled_commit
from amule_bump.domain.bump_error import BumpError
from amule_bump.domain.dockerfile import Pin, read_pin, rewrite_pin
from amule_bump.ports.driven.dockerfile import DockerfileReader, DockerfileWriter
from amule_bump.ports.driven.pull_request_body_writer import PullRequestBodyWriter
from amule_bump.ports.driven.repo_reader import RepoReader
from amule_bump.ports.driven.step_output_writer import StepOutputWriter


def main(
    dockerfile: PurePath,
    body_file: PurePath,
    dry_run: bool,
    *,
    repo_reader: RepoReader,
    dockerfile_reader: DockerfileReader,
    dockerfile_writer: DockerfileWriter,
    pull_request_body_writer: PullRequestBodyWriter,
    step_output_writer: StepOutputWriter,
) -> int:
    """Prints a bump error and returns 1."""
    try:
        return _bump(
            dockerfile,
            body_file,
            dry_run,
            repo_reader,
            dockerfile_reader,
            dockerfile_writer,
            pull_request_body_writer,
            step_output_writer,
        )
    except (BumpError, OSError) as error:  # OSError covers urllib errors and a missing file
        print(f"error: {error}", file=sys.stderr)
        return 1


def _bump(
    dockerfile: PurePath,
    body_file: PurePath,
    dry_run: bool,
    repo_reader: RepoReader,
    dockerfile_reader: DockerfileReader,
    dockerfile_writer: DockerfileWriter,
    pull_request_body_writer: PullRequestBodyWriter,
    step_output_writer: StepOutputWriter,
) -> int:
    dockerfile_text = dockerfile_reader.read_dockerfile(dockerfile)
    old = read_pin(dockerfile_text)
    latest = latest_release_tag(repo_reader)
    if latest == old.version:
        print(f"aMule {old.version} is the latest release: nothing to do")
        return 0
    if not is_newer(latest, old.version):
        print(
            f"latest upstream release {latest} is older than the pinned {old.version}:"
            " nothing to do"
        )
        return 0

    new = Pin(latest, peeled_commit(repo_reader, latest))
    body = build_pull_request_body(repo_reader, old, new)
    if dry_run:
        print(new.arg_lines())
        print(f"--- PR body ({len(body)} characters) ---")
        print(body, end="")
        return 0

    dockerfile_writer.write_dockerfile(dockerfile, rewrite_pin(dockerfile_text, new))
    pull_request_body_writer.write_pull_request_body(body_file, body)
    step_output_writer.write_step_outputs(new.version, body_file)
    return 0
