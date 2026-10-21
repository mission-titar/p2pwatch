"""``python -m coverage_checks``: hands the check to the command line."""

import functools
import tempfile
from collections.abc import Sequence
from pathlib import Path

from coverage_checks.adapters.driven.coverage_py_reader import CoveragePyReader
from coverage_checks.adapters.driven.filesystem_package_tree_reader import (
    FilesystemPackageTreeReader,
)
from coverage_checks.adapters.driving import unit_coverage
from coverage_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from coverage_checks.application.check_unit_coverage import CheckUnitCoverage


def main(argv: Sequence[str] | None = None) -> int:
    """Runs the subcommand ``argv`` names (``sys.argv`` when ``None``), returns its exit code."""
    package_directory = Path.cwd()
    with tempfile.TemporaryDirectory() as report_directory:
        unit_coverage_checker = CheckUnitCoverage(
            package_tree_reader=FilesystemPackageTreeReader(package_directory=package_directory),
            test_coverage_reader=CoveragePyReader(
                package_directory=package_directory,
                data_file=package_directory / ".coverage",
                report_directory=Path(report_directory),
            ),
        )
        return ArgparseCommandLine(
            check_unit_coverage=functools.partial(
                unit_coverage.main, unit_coverage_checker=unit_coverage_checker
            )
        ).run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
