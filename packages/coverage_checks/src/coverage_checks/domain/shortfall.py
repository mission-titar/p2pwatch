"""What of a module its own tests leave unrun, but the top-level code the test run ran."""

from collections.abc import Sequence
from pathlib import PurePath

from coverage_checks.domain.function_bodies import find_function_body_lines
from coverage_checks.domain.test_coverage import TestCoverage


def find_shortfall(
    module: PurePath,
    own_test_files: Sequence[PurePath],
    test_coverage: TestCoverage,
    source: str,
) -> str | None:
    """The problem naming what of *module*, whose text is *source*, its own tests leave unrun."""
    body_lines = find_function_body_lines(source)
    statements = sorted(
        statement
        for statement in test_coverage.statements - test_coverage.statements_run_by_own_tests
        if statement in body_lines or statement not in test_coverage.statements_run
    )
    branches = sorted(
        branch
        for branch in test_coverage.branches - test_coverage.branches_run_by_own_tests
        if branch[0] in body_lines or branch not in test_coverage.branches_run
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
    own_test_names = (
        ", ".join(test_file.as_posix() for test_file in own_test_files) or "it has none"
    )
    return f"{module}: {' and '.join(unrun)} run by none of its own tests ({own_test_names})"
