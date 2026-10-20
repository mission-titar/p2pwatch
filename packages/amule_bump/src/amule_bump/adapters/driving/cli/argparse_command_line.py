"""The command line: parses a subcommand, calls the bumper, prints its answer."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import PurePath
from typing import assert_never

from amule_bump.domain.bump_error import BumpError
from amule_bump.ports.driving.amule_bumper import (
    AmuleBump,
    AmuleBumper,
    PinAheadOfLatest,
    PinIsLatest,
)


class ArgparseCommandLine:
    """``bump``, over the Dockerfile it rewrites and the file it writes the PR body to; a
    relative path is taken under ``cwd``, the body's default in ``temporary_directory``."""

    def __init__(
        self, *, amule_bumper: AmuleBumper, cwd: PurePath, temporary_directory: PurePath
    ) -> None:
        self._amule_bumper = amule_bumper
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
        try:
            outcome = self._amule_bumper.bump_amule(
                args.dockerfile, args.body_file, dry_run=args.dry_run
            )
        except (BumpError, OSError) as error:  # OSError covers urllib errors and a missing file
            print(f"error: {error}", file=sys.stderr)
            return 1
        match outcome:
            case PinIsLatest(version=version):
                print(f"aMule {version} is the latest release: nothing to do")
            case PinAheadOfLatest(pinned_version=pinned_version, latest_version=latest_version):
                print(
                    f"latest upstream release {latest_version} is older than the pinned"
                    f" {pinned_version}: nothing to do"
                )
            case AmuleBump(new_pin=new_pin, body=body):
                if args.dry_run:
                    print(new_pin.arg_lines())
                    print(f"--- PR body ({len(body)} characters) ---")
                    print(body, end="")
            case _:  # pragma: no cover
                assert_never(outcome)
        return 0

    def _under_cwd(self, path: str) -> PurePath:
        """``path`` under ``cwd``, or as it is when absolute."""
        return self._cwd / path
