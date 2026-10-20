"""``python -m amule_bump``: hands the bump, reading upstream on GitHub, to the command line."""

import functools
import os
from collections.abc import Sequence
from pathlib import Path

from amule_bump.adapters.driven.filesystem_dockerfile import FilesystemDockerfile
from amule_bump.adapters.driven.filesystem_pull_request_body_writer import (
    FilesystemPullRequestBodyWriter,
)
from amule_bump.adapters.driven.github_repo_reader import GitHubRepoReader
from amule_bump.adapters.driven.github_step_output_writer import GitHubStepOutputWriter
from amule_bump.adapters.driving import bump
from amule_bump.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from amule_bump.domain.upstream import UPSTREAM


def main(argv: Sequence[str] | None = None) -> int:
    """Runs the subcommand ``argv`` names (``sys.argv`` when ``None``), returns its exit code."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    dockerfile = FilesystemDockerfile()
    bump_pin = functools.partial(
        bump.main,
        repo_reader=GitHubRepoReader(UPSTREAM, os.environ.get("GH_TOKEN")),
        dockerfile_reader=dockerfile,
        dockerfile_writer=dockerfile,
        pull_request_body_writer=FilesystemPullRequestBodyWriter(),
        step_output_writer=GitHubStepOutputWriter(Path(github_output) if github_output else None),
    )
    return ArgparseCommandLine(bump_pin=bump_pin).run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
