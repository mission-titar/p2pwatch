"""The command line: parses a subcommand, calls the bump, returns the exit code."""

import argparse
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path


class ArgparseCommandLine:
    """``bump``, over the Dockerfile it rewrites and the file it writes the PR body to."""

    def __init__(self, *, bump_pin: Callable[[Path, Path, bool], int]) -> None:
        self._bump_pin = bump_pin

    def run(self, argv: Sequence[str] | None = None) -> int:
        """Runs the subcommand ``argv`` names (``sys.argv`` if ``None``), returns its exit code."""
        parser = argparse.ArgumentParser(
            prog="amule_bump", description="bump the aMule image's pin to upstream's latest release"
        )
        subparsers = parser.add_subparsers(dest="command", required=True)
        bump = subparsers.add_parser(
            "bump", help="rewrite the Dockerfile's pin and write the PR body, if upstream released"
        )
        bump.add_argument("--dockerfile", type=Path, default=Path("packages/amule/Dockerfile"))
        bump.add_argument(
            "--body-file", type=Path, default=Path(tempfile.gettempdir()) / "amule-bump-pr-body.md"
        )
        bump.add_argument(
            "--dry-run",
            action="store_true",
            help="print the new pin and the PR body, write nothing",
        )
        args = parser.parse_args(argv)
        return self._bump_pin(args.dockerfile, args.body_file, args.dry_run)
