"""Bump aMule's Dockerfile pin to the latest upstream release and write the PR body.

The workflow opens the PR afterwards, from the `version` and `body-path` step outputs.
"""

import sys
from pathlib import Path

from amule_bump.application.body import build_pull_request_body
from amule_bump.application.release import is_newer, latest_release_tag, peeled_commit
from amule_bump.domain.bump_error import BumpError
from amule_bump.domain.dockerfile import Pin, read_pin, rewrite_pin
from amule_bump.ports.driven.repo_reader import RepoReader


def main(
    dockerfile: Path,
    body_file: Path,
    dry_run: bool,
    *,
    repo_reader: RepoReader,
    github_output: str | None,
) -> int:
    """Prints a bump error and returns 1; ``github_output`` is Actions' step-outputs file."""
    try:
        return _bump(dockerfile, body_file, dry_run, repo_reader, github_output)
    except (BumpError, OSError) as error:  # OSError covers urllib errors and a missing file
        print(f"error: {error}", file=sys.stderr)
        return 1


def _bump(
    dockerfile: Path,
    body_file: Path,
    dry_run: bool,
    repo_reader: RepoReader,
    github_output: str | None,
) -> int:
    dockerfile_text = dockerfile.read_text()
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

    dockerfile.write_text(rewrite_pin(dockerfile_text, new))
    body_file.write_text(body)
    _write_step_outputs(github_output, new.version, body_file)
    return 0


def _write_step_outputs(github_output: str | None, version: str, body_file: Path) -> None:
    """Hand the new version and the body's path to the workflow's next step, when in Actions."""
    if github_output:
        with open(github_output, "a") as output:
            output.write(f"version={version}\nbody-path={body_file}\n")
