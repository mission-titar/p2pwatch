"""Each module's statements and branches are run by its own tests, what an import runs aside.

Run in a package's directory, once its pytest has recorded per-test contexts (`--cov-context`).
"""

import json
import re
import sys
import tempfile
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from coverage import Coverage

from coverage_checks.adapters.driven.own_tests import find_own_tests
from coverage_checks.domain.function_bodies import find_function_body_lines

type Branch = tuple[int, int]


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
    own_tests = find_own_tests(_read_tests_without_unit())
    with tempfile.TemporaryDirectory() as report_dir:
        report = Path(report_dir) / "coverage.json"
        shortfalls = [
            shortfall
            for module, test_files in own_tests.test_files_by_module.items()
            if (shortfall := _find_shortfall(coverage, report, module, test_files))
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


def _read_tests_without_unit() -> dict[str, object]:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    tests_without_unit: dict[str, object] = (
        pyproject.get("tool", {}).get("coverage_checks", {}).get("tests_without_unit", {})
    )
    return tests_without_unit


def _find_shortfall(
    coverage: Coverage, report: Path, module: Path, test_files: Sequence[Path]
) -> str | None:
    """What of *module* its own tests leave unrun, but the top-level code any test ran."""
    every_test = _read_execution(coverage, report, module, contexts=None)
    own_contexts = [f"^{re.escape(test_file.as_posix())}::" for test_file in test_files]
    own_run = (
        _read_execution(coverage, report, module, own_contexts) if own_contexts else _NOTHING_RUN
    )
    body_lines = find_function_body_lines(module.read_text(encoding="utf-8"))
    statements = sorted(
        statement
        for statement in every_test.statements - own_run.run_statements
        if statement in body_lines or statement not in every_test.run_statements
    )
    branches = sorted(
        branch
        for branch in every_test.branches - own_run.run_branches
        if branch[0] in body_lines or branch not in every_test.run_branches
    )
    unrun = [
        f"{kind} {', '.join(labels)}"
        for kind, labels in (
            ("statements", [str(statement) for statement in statements]),
            ("branches", [f"{start}->{end if end > 0 else 'exit'}" for start, end in branches]),
        )
        if labels
    ]
    if not unrun:
        return None
    own_test_names = ", ".join(test_file.as_posix() for test_file in test_files) or "it has none"
    return f"{module}: {' and '.join(unrun)} run by none of its own tests ({own_test_names})"


def _read_execution(
    coverage: Coverage, report: Path, module: Path, contexts: list[str] | None
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
