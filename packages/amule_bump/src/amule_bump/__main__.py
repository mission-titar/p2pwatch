"""``python -m amule_bump``: hands the bump, reading upstream on GitHub, to the command line."""

import functools
import os
from collections.abc import Sequence

from amule_bump.adapters.driven.github_repo_reader import GitHubRepoReader
from amule_bump.adapters.driving import bump
from amule_bump.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from amule_bump.domain.upstream import UPSTREAM


def main(argv: Sequence[str] | None = None) -> int:
    """Runs the subcommand ``argv`` names (``sys.argv`` when ``None``), returns its exit code."""
    bump_pin = functools.partial(
        bump.main,
        repo_reader=GitHubRepoReader(UPSTREAM, os.environ.get("GH_TOKEN")),
        github_output=os.environ.get("GITHUB_OUTPUT"),
    )
    return ArgparseCommandLine(bump_pin=bump_pin).run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
