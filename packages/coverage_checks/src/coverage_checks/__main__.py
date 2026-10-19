"""``python -m coverage_checks``: hands the check to the command line."""

from collections.abc import Sequence

from coverage_checks.adapters.driving import unit_coverage
from coverage_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine


def main(argv: Sequence[str] | None = None) -> int:
    """Runs the subcommand ``argv`` names (``sys.argv`` when ``None``), returns its exit code."""
    return ArgparseCommandLine(check_unit_coverage=unit_coverage.main).run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
