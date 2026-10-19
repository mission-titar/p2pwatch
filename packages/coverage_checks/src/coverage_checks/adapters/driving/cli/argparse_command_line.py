"""The command line: parses a subcommand, calls its check, returns the exit code."""

import argparse
from collections.abc import Callable, Sequence


class ArgparseCommandLine:
    """``unit-coverage``, run in a package's directory once its pytest has recorded coverage."""

    def __init__(self, *, check_unit_coverage: Callable[[], int]) -> None:
        self._check_unit_coverage = check_unit_coverage

    def run(self, argv: Sequence[str] | None = None) -> int:
        """Runs the subcommand ``argv`` names (``sys.argv`` if ``None``), returns its exit code."""
        parser = argparse.ArgumentParser(
            prog="coverage_checks", description="check each module is covered by its own tests"
        )
        subparsers = parser.add_subparsers(dest="command", required=True)
        subparsers.add_parser(
            "unit-coverage", help="check each module's code is run by its own tests"
        )
        parser.parse_args(argv)
        return self._check_unit_coverage()
