import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath

from coverage import Coverage
from coverage.exceptions import CoverageException

from coverage_checks.application.ports.driven.test_coverage_reader import TestCoverageReader
from coverage_checks.domain.broken_input_error import BrokenInputError
from coverage_checks.domain.test_coverage import Branch, TestCoverage


@dataclass(frozen=True)
class _Analysis:
    """A module's statements and branches, and those the selected tests ran."""

    statements: frozenset[int]
    branches: frozenset[Branch]
    statements_run: frozenset[int]
    branches_run: frozenset[Branch]


_NOTHING_RUN = _Analysis(frozenset(), frozenset(), frozenset(), frozenset())


class CoveragePyTestCoverageReader(TestCoverageReader):
    """A coverage.py data file of one context per test, `tests/a/test_b.py::test_c|run` as
    pytest-cov's `--cov-context=test` names them, analysed under the package's `pyproject.toml`."""

    def __init__(self, *, package_directory: Path, data_file: Path, report_directory: Path) -> None:
        self._package_directory = package_directory
        self._data_file = data_file
        self._report_file = report_directory / "coverage.json"

    def read_test_coverage_by_module(
        self, own_test_files_by_module: Mapping[PurePath, Sequence[PurePath]]
    ) -> dict[PurePath, TestCoverage]:
        coverage = self._load()
        return {
            module: self._read_test_coverage(coverage, module, own_test_files)
            for module, own_test_files in own_test_files_by_module.items()
        }

    def _read_test_coverage(
        self, coverage: Coverage, module: PurePath, own_test_files: Sequence[PurePath]
    ) -> TestCoverage:
        run = self._analyze(coverage, module, contexts=None)
        own_contexts = [f"^{re.escape(test_file.as_posix())}::" for test_file in own_test_files]
        # An empty list of contexts would select every test.
        run_by_own_tests = (
            self._analyze(coverage, module, own_contexts) if own_contexts else _NOTHING_RUN
        )
        return TestCoverage(
            statements=run.statements,
            branches=run.branches,
            statements_run=run.statements_run,
            branches_run=run.branches_run,
            statements_run_by_own_tests=run_by_own_tests.statements_run,
            branches_run_by_own_tests=run_by_own_tests.branches_run,
        )

    def _load(self) -> Coverage:
        """The run's coverage, once it holds branches and each test apart."""
        # coverage.py's errors name the file they could not use.
        try:
            coverage = Coverage(
                data_file=str(self._data_file),
                config_file=str(self._package_directory / "pyproject.toml"),
            )
        except CoverageException as error:
            raise BrokenInputError(str(error)) from error
        try:
            coverage.load()
        except CoverageException as error:
            coverage.get_data().close(force=True)  # coverage.py leaves a non-database open
            raise BrokenInputError(str(error)) from error
        coverage_data = coverage.get_data()
        if not coverage_data.has_arcs() or not coverage_data.measured_contexts() - {""}:
            raise BrokenInputError(
                f"{self._data_file}: no per-test branch coverage; run this package's pytest"
                " first, with branch coverage and --cov-context=test"
            )
        return coverage

    def _analyze(
        self, coverage: Coverage, module: PurePath, contexts: list[str] | None
    ) -> _Analysis:
        """coverage.py's own analysis of *module*, restricted to the tests matching *contexts*."""
        try:
            coverage.json_report(
                morfs=[str(self._package_directory / module)],
                outfile=str(self._report_file),
                contexts=contexts,
            )
        except CoverageException as error:
            raise BrokenInputError(str(error)) from error
        (measured,) = json.loads(self._report_file.read_text(encoding="utf-8"))["files"].values()
        return _Analysis(
            statements=frozenset(measured["executed_lines"] + measured["missing_lines"]),
            branches=_branches(measured["executed_branches"] + measured["missing_branches"]),
            statements_run=frozenset(measured["executed_lines"]),
            branches_run=_branches(measured["executed_branches"]),
        )


def _branches(start_and_end_pairs: list[list[int]]) -> frozenset[Branch]:
    return frozenset((start, end) for start, end in start_and_end_pairs)
