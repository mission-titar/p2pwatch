"""Each module's statements and branches are run by its own tests, what an import runs aside.

Run in a package's directory, once its pytest has recorded per-test contexts (`--cov-context`).
"""

import json
import re
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath

from coverage import Coverage

from coverage_checks.adapters.driven.filesystem_package_tree_reader import (
    FilesystemPackageTreeReader,
)
from coverage_checks.domain.own_tests import find_own_tests
from coverage_checks.domain.shortfall import find_shortfall
from coverage_checks.domain.test_coverage import Branch, TestCoverage


@dataclass(frozen=True)
class _Execution:
    """A module's statements and branches, and those some tests ran."""

    statements: frozenset[int]
    run_statements: frozenset[int]
    branches: frozenset[Branch]
    run_branches: frozenset[Branch]


_NOTHING_RUN = _Execution(frozenset(), frozenset(), frozenset(), frozenset())


def main() -> int:
    """Prints each problem and a summary, returns 1 on any problem."""
    coverage = Coverage()
    coverage.load()
    coverage_data = coverage.get_data()
    if not coverage_data.has_arcs() or not coverage_data.measured_contexts() - {""}:
        print(
            f"no per-test branch coverage in {coverage.get_option('run:data_file')}: run this"
            " package's pytest first, with branch coverage and --cov-context=test",
            file=sys.stderr,
        )
        return 1
    package_tree_reader = FilesystemPackageTreeReader(package_directory=Path.cwd())
    own_tests = find_own_tests(package_tree_reader.read_package_tree())
    with tempfile.TemporaryDirectory() as report_dir:
        report = Path(report_dir) / "coverage.json"
        shortfalls = [
            shortfall
            for module, test_files in own_tests.test_files_by_module.items()
            if (
                shortfall := find_shortfall(
                    module,
                    test_files,
                    _read_test_coverage(coverage, report, module, test_files),
                    Path(module).read_text(encoding="utf-8"),
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


def _read_test_coverage(
    coverage: Coverage, report: Path, module: PurePath, test_files: Sequence[PurePath]
) -> TestCoverage:
    run = _read_execution(coverage, report, module, contexts=None)
    own_contexts = [f"^{re.escape(test_file.as_posix())}::" for test_file in test_files]
    own_run = (
        _read_execution(coverage, report, module, own_contexts) if own_contexts else _NOTHING_RUN
    )
    return TestCoverage(
        statements=run.statements,
        branches=run.branches,
        statements_run=run.run_statements,
        branches_run=run.run_branches,
        statements_run_by_own_tests=own_run.run_statements,
        branches_run_by_own_tests=own_run.run_branches,
    )


def _read_execution(
    coverage: Coverage, report: Path, module: PurePath, contexts: list[str] | None
) -> _Execution:
    """coverage.py's own analysis of *module*, restricted to the tests matching *contexts*."""
    coverage.json_report(morfs=[str(module)], outfile=str(report), contexts=contexts)
    (measured,) = json.loads(report.read_text(encoding="utf-8"))["files"].values()
    return _Execution(
        statements=frozenset(measured["executed_lines"] + measured["missing_lines"]),
        run_statements=frozenset(measured["executed_lines"]),
        branches=frozenset(
            (start, end)
            for start, end in measured["executed_branches"] + measured["missing_branches"]
        ),
        run_branches=frozenset((start, end) for start, end in measured["executed_branches"]),
    )
