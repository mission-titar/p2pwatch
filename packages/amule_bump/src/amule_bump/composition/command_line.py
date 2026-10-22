"""The command line of ``python -m amule_bump``, on the bump reading upstream on GitHub."""

from collections.abc import Mapping
from pathlib import Path
from urllib.request import OpenerDirector, build_opener

from amule_bump.adapters.driven.filesystem_dockerfile import FilesystemDockerfile
from amule_bump.adapters.driven.filesystem_pull_request_body_writer import (
    FilesystemPullRequestBodyWriter,
)
from amule_bump.adapters.driven.github_repo_reader import GitHubRepoReader
from amule_bump.adapters.driven.github_step_output_writer import GitHubStepOutputWriter
from amule_bump.adapters.driven.terminal_step_output_writer import TerminalStepOutputWriter
from amule_bump.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from amule_bump.application.use_cases.bump_amule import BumpAmule
from amule_bump.domain.upstream import UPSTREAM

_CHANGELOG_WIDTH_CHARACTERS = 100
_GITHUB_API_URL = "https://api.github.com"


def build_command_line(
    *, env: Mapping[str, str], cwd: Path, temporary_directory: Path
) -> ArgparseCommandLine:
    """The command line run in the environment ``env``, a relative path under ``cwd``, the PR
    body by default in ``temporary_directory``."""
    return ArgparseCommandLine(
        amule_bumper=build_amule_bumper(
            env=env,
            github_api_url=_GITHUB_API_URL,
            url_opener=build_opener(),  # the environment's proxies, wanted for GitHub
        ),
        cwd=cwd,
        temporary_directory=temporary_directory,
    )


def build_amule_bumper(
    *, env: Mapping[str, str], github_api_url: str, url_opener: OpenerDirector
) -> BumpAmule:
    """The bump run in the environment ``env``, GitHub at ``github_api_url`` by ``url_opener``."""
    dockerfile = FilesystemDockerfile()
    github_output = env.get("GITHUB_OUTPUT")
    return BumpAmule(
        repo_reader=GitHubRepoReader(github_api_url, UPSTREAM, env.get("GH_TOKEN"), url_opener),
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
