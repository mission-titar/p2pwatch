"""What of a module its own tests leave unrun, but the top-level code the test run ran."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePath

from coverage_checks.domain.function_bodies import find_function_body_lines
from coverage_checks.domain.test_coverage import Branch, TestCoverage


@dataclass(kw_only=True, frozen=True)
class Shortfall:
    """What of a module its own tests leave unrun, in line order, and those own tests."""

    module: PurePath
    own_test_files: tuple[PurePath, ...]
    unrun_statements: tuple[int, ...]
    unrun_branches: tuple[Branch, ...]


def find_shortfall(
    module: PurePath,
    *,
    own_test_files: Sequence[PurePath],
    test_coverage: TestCoverage,
    source: str,
) -> Shortfall | None:
    """What of *module*, whose text is *source*, its own tests leave unrun, if anything."""
    body_lines = find_function_body_lines(source)
    unrun_statements = tuple(
        sorted(
            statement
            for statement in test_coverage.statements - test_coverage.statements_run_by_own_tests
            if statement in body_lines or statement not in test_coverage.statements_run
        )
    )
    unrun_branches = tuple(
        sorted(
            branch
            for branch in test_coverage.branches - test_coverage.branches_run_by_own_tests
            if branch[0] in body_lines or branch not in test_coverage.branches_run
        )
    )
    if not unrun_statements and not unrun_branches:
        return None
    return Shortfall(
        module=module,
        own_test_files=tuple(own_test_files),
        unrun_statements=unrun_statements,
        unrun_branches=unrun_branches,
    )
