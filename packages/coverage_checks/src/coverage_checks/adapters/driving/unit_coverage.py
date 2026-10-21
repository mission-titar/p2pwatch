"""Each module's statements and branches are run by its own tests, what an import runs aside.

Run in a package's directory, once its pytest has recorded per-test contexts (`--cov-context`).
"""

import sys
import tempfile
from pathlib import Path

from coverage_checks.adapters.driven.coverage_py_reader import CoveragePyReader
from coverage_checks.adapters.driven.filesystem_package_tree_reader import (
    FilesystemPackageTreeReader,
)
from coverage_checks.domain.own_tests import find_own_tests
from coverage_checks.domain.shortfall import find_shortfall


def main() -> int:
    """Prints each problem and a summary, returns 1 on any problem."""
    package_directory = Path.cwd()
    data_file = package_directory / ".coverage"
    with tempfile.TemporaryDirectory() as report_directory:
        test_coverage_reader = CoveragePyReader(
            package_directory=package_directory,
            data_file=data_file,
            report_directory=Path(report_directory),
        )
        if not test_coverage_reader.has_per_test_branch_coverage():
            print(
                f"no per-test branch coverage in {data_file.name}: run this"
                " package's pytest first, with branch coverage and --cov-context=test",
                file=sys.stderr,
            )
            return 1
        package_tree_reader = FilesystemPackageTreeReader(package_directory=package_directory)
        own_tests = find_own_tests(package_tree_reader.read_package_tree())
        shortfalls = [
            shortfall
            for module, test_files in own_tests.test_files_by_module.items()
            if (
                shortfall := find_shortfall(
                    module,
                    test_files,
                    test_coverage_reader.read_test_coverage(module, test_files),
                    package_tree_reader.read_module_source(module),
                )
            )
        ]
    problems = [*own_tests.problems, *shortfalls]
    for problem in problems:
        print(problem)
    tested_modules = [module for module, files in own_tests.test_files_by_module.items() if files]
    module_count = len(own_tests.test_files_by_module)
    print(
        f"{Path.cwd().name}: {own_tests.mapped_test_count} test files map to"
        f" {len(tested_modules)} of {module_count} modules, {own_tests.listed_test_count} are"
        f" listed without a unit; {len(shortfalls)} of {module_count} modules short of their"
        " own tests"
    )
    return 1 if problems else 0
