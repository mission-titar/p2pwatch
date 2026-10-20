"""``python -m amule_bump``: hands the bump, reading upstream on GitHub, to the command line."""

import functools
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from amule_bump.adapters.driven.filesystem_dockerfile import FilesystemDockerfile
from amule_bump.adapters.driven.filesystem_pull_request_body_writer import (
    FilesystemPullRequestBodyWriter,
)
from amule_bump.adapters.driven.github_repo_reader import GitHubRepoReader
from amule_bump.adapters.driven.github_step_output_writer import GitHubStepOutputWriter
from amule_bump.adapters.driven.terminal_step_output_writer import TerminalStepOutputWriter
from amule_bump.adapters.driving import bump
from amule_bump.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from amule_bump.domain.upstream import UPSTREAM

_CHANGELOG_WIDTH_CHARACTERS = 100


def main(argv: Sequence[str], env: Mapping[str, str], cwd: Path, temporary_directory: Path) -> int:
    """Runs the subcommand ``argv`` names in the environment ``env``, a relative path under
    ``cwd``, the PR body by default in ``temporary_directory``; returns its exit code."""
    dockerfile = FilesystemDockerfile()
    github_output = env.get("GITHUB_OUTPUT")
    bump_pin = functools.partial(
        bump.main,
        repo_reader=GitHubRepoReader(UPSTREAM, env.get("GH_TOKEN")),
        dockerfile_reader=dockerfile,
        dockerfile_writer=dockerfile,
        pull_request_body_writer=FilesystemPullRequestBodyWriter(),
        step_output_writer=(
            GitHubStepOutputWriter(Path(github_output))
            if github_output
            else TerminalStepOutputWriter()
        ),
        changelog_width_characters=_CHANGELOG_WIDTH_CHARACTERS,
    )
    command_line = ArgparseCommandLine(
        bump_pin=bump_pin, cwd=cwd, temporary_directory=temporary_directory
    )
    return command_line.run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:], os.environ, Path.cwd(), Path(tempfile.gettempdir())))
