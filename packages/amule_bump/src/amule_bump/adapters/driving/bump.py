"""Bump aMule's Dockerfile pin to the latest upstream release and write the PR body.

The workflow opens the PR afterwards, from the `version` and `body-path` step outputs.
"""

import argparse
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

from amule_bump.adapters.driven.github_repo_reader import GitHubRepoReader
from amule_bump.application.body import build_pull_request_body
from amule_bump.application.release import is_newer, latest_release_tag, peeled_commit
from amule_bump.domain.bump_error import BumpError
from amule_bump.domain.dockerfile import Pin, read_pin, rewrite_pin
from amule_bump.domain.upstream import UPSTREAM
from amule_bump.ports.driven.repo_reader import RepoReader


def main(
    argv: list[str] | None = None,
    repo_reader: RepoReader | None = None,
    env: Mapping[str, str] = os.environ,
) -> int:
    args = _parse_args(argv)
    repo_reader = repo_reader or GitHubRepoReader(UPSTREAM, env.get("GH_TOKEN"))
    try:
        return _bump(args, repo_reader, env)
    except (BumpError, OSError) as error:  # OSError covers urllib errors and a missing file
        print(f"error: {error}", file=sys.stderr)
        return 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m amule_bump.adapters.driving.bump", description=__doc__
    )
    parser.add_argument("--dockerfile", type=Path, default=Path("packages/amule/Dockerfile"))
    parser.add_argument(
        "--body-file", type=Path, default=Path(tempfile.gettempdir()) / "amule-bump-pr-body.md"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the new pin and the PR body, write nothing"
    )
    return parser.parse_args(argv)


def _bump(args: argparse.Namespace, repo_reader: RepoReader, env: Mapping[str, str]) -> int:
    dockerfile_text = args.dockerfile.read_text()
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
    if args.dry_run:
        print(new.arg_lines())
        print(f"--- PR body ({len(body)} characters) ---")
        print(body, end="")
        return 0

    args.dockerfile.write_text(rewrite_pin(dockerfile_text, new))
    args.body_file.write_text(body)
    _write_step_outputs(env.get("GITHUB_OUTPUT"), new.version, args.body_file)
    return 0


def _write_step_outputs(github_output: str | None, version: str, body_file: Path) -> None:
    """Hand the new version and the body's path to the workflow's next step, when in Actions."""
    if github_output:
        with open(github_output, "a") as output:
            output.write(f"version={version}\nbody-path={body_file}\n")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
