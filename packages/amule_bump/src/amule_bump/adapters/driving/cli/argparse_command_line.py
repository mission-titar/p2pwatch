"""The command line: parses a subcommand, calls the bump, returns the exit code."""

import argparse
from collections.abc import Callable, Sequence
from pathlib import PurePath


class ArgparseCommandLine:
    """``bump``, over the Dockerfile it rewrites and the file it writes the PR body to; a
    relative path is taken under ``cwd``, the body's default in ``temporary_directory``."""

    def __init__(
        self,
        *,
        bump_pin: Callable[[PurePath, PurePath, bool], int],
        cwd: PurePath,
        temporary_directory: PurePath,
    ) -> None:
        self._bump_pin = bump_pin
        self._cwd = cwd
        self._temporary_directory = temporary_directory

    def run(self, argv: Sequence[str]) -> int:
        """Runs the subcommand ``argv`` names, returns its exit code."""
        parser = argparse.ArgumentParser(
            prog="amule_bump", description="bump the aMule image's pin to upstream's latest release"
        )
        subparsers = parser.add_subparsers(dest="command", required=True)
        bump = subparsers.add_parser(
            "bump", help="rewrite the Dockerfile's pin and write the PR body, if upstream released"
        )
        bump.add_argument(
            "--dockerfile", type=self._under_cwd, default=self._cwd / "packages/amule/Dockerfile"
        )
        bump.add_argument(
            "--body-file",
            type=self._under_cwd,
            default=self._temporary_directory / "amule-bump-pr-body.md",
        )
        bump.add_argument(
            "--dry-run",
            action="store_true",
            help="print the new pin and the PR body, write nothing",
        )
        args = parser.parse_args(argv)
        return self._bump_pin(args.dockerfile, args.body_file, args.dry_run)

    def _under_cwd(self, path: str) -> PurePath:
        """``path`` under ``cwd``, or as it is when absolute."""
        return self._cwd / path
