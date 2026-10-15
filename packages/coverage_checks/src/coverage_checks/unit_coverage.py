"""A package's test files mirror its `src`: each tests the module it is named after, or is listed.

Run in a package's directory: `python -m coverage_checks.unit_coverage`.
"""

import sys
import tomllib
from pathlib import Path

from coverage_checks.own_tests import find_own_tests


def main() -> None:
    """CLI entry point: prints each problem and a summary, exits 1 on any problem."""
    own_tests = find_own_tests(_read_tests_without_unit())
    for problem in own_tests.problems:
        print(problem)
    tested_modules = [module for module, files in own_tests.test_files_by_module.items() if files]
    print(
        f"{Path.cwd().name}: {own_tests.mapped_test_count} test files map to"
        f" {len(tested_modules)} of {len(own_tests.test_files_by_module)} modules,"
        f" {own_tests.listed_test_count} are listed without a unit"
    )
    if own_tests.problems:
        sys.exit(1)


def _read_tests_without_unit() -> dict[str, object]:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    tests_without_unit: dict[str, object] = (
        pyproject.get("tool", {}).get("coverage_checks", {}).get("tests_without_unit", {})
    )
    return tests_without_unit


if __name__ == "__main__":
    main()  # pragma: no cover
