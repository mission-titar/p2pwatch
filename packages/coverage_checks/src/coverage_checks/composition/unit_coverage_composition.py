"""The check on the real readers, coverage.py's report in a directory that lives for one check."""

from pathlib import Path
from tempfile import TemporaryDirectory

from coverage_checks.adapters.driven.coverage_py_test_coverage_reader import (
    CoveragePyTestCoverageReader,
)
from coverage_checks.adapters.driven.filesystem_package_tree_reader import (
    FilesystemPackageTreeReader,
)
from coverage_checks.application.ports.driving.unit_coverage_checker import (
    UnitCoverageChecker,
    UnitCoverageReport,
)
from coverage_checks.application.use_cases.check_unit_coverage import CheckUnitCoverage


class UnitCoverageComposition(UnitCoverageChecker):
    """Checks the package in ``package_directory`` against ``data_file``, the report directory
    made in ``temporary_directory`` and removed once the check returns."""

    def __init__(
        self, *, package_directory: Path, data_file: Path, temporary_directory: Path
    ) -> None:
        self._package_directory = package_directory
        self._data_file = data_file
        self._temporary_directory = temporary_directory

    def check_unit_coverage(self) -> UnitCoverageReport:
        with TemporaryDirectory(dir=self._temporary_directory) as report_directory:
            return CheckUnitCoverage(
                package_tree_reader=FilesystemPackageTreeReader(
                    package_directory=self._package_directory
                ),
                test_coverage_reader=CoveragePyTestCoverageReader(
                    package_directory=self._package_directory,
                    data_file=self._data_file,
                    report_directory=Path(report_directory),
                ),
            ).check_unit_coverage()
