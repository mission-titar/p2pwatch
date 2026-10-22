"""``python -m coverage_checks``: hands the check to the command line."""

import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from coverage_checks.adapters.driven.coverage_py_reader import CoveragePyReader
from coverage_checks.adapters.driven.filesystem_package_tree_reader import (
    FilesystemPackageTreeReader,
)
from coverage_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from coverage_checks.application.use_cases.check_unit_coverage import CheckUnitCoverage


def main(argv: Sequence[str], cwd: Path, report_directory: Path) -> int:
    """Runs the subcommand ``argv`` names on the package whose directory is ``cwd``, coverage.py's
    report in ``report_directory``; returns its exit code."""
    data_file = cwd / ".coverage"  # where pytest-cov records, run in the package's directory
    command_line = ArgparseCommandLine(
        unit_coverage_checker=CheckUnitCoverage(
            package_tree_reader=FilesystemPackageTreeReader(package_directory=cwd),
            test_coverage_reader=CoveragePyReader(
                package_directory=cwd, data_file=data_file, report_directory=report_directory
            ),
        ),
        package_name=cwd.name,
        data_file=data_file,
    )
    return command_line.run(argv)


if __name__ == "__main__":  # pragma: no cover
    with tempfile.TemporaryDirectory() as report_directory:
        raise SystemExit(main(sys.argv[1:], Path.cwd(), Path(report_directory)))
