"""The command line of ``python -m coverage_checks``, on the check's composition."""

from pathlib import Path

from coverage_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from coverage_checks.composition.unit_coverage_composition import UnitCoverageComposition


def build_command_line(*, cwd: Path, temporary_directory: Path) -> ArgparseCommandLine:
    """The command line checking the package whose directory is ``cwd``, coverage.py's report in
    ``temporary_directory``."""
    data_file = cwd / ".coverage"  # where pytest-cov records, run in the package's directory
    return ArgparseCommandLine(
        unit_coverage_checker=UnitCoverageComposition(
            package_directory=cwd, data_file=data_file, temporary_directory=temporary_directory
        ),
        package_name=cwd.name,
        data_file=data_file,
    )
