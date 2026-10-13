"""CLI gate: assert every source-family VEX claim still holds against our tree.

Exits non-zero (and prints a GitHub ``::error::`` annotation per breach) if any
source guard's premise is contradicted by the shipped source.
"""

import sys

from vex_guards.descriptors import SourceGuard, is_source_guard
from vex_guards.registry import GUARDS
from vex_guards.repo import source_dirs
from vex_guards.source_scan import evaluate_source_guards


def main() -> int:
    guards: dict[str, SourceGuard] = {
        advisory_id: guard for advisory_id, guard in GUARDS.items() if is_source_guard(guard)
    }
    violations = evaluate_source_guards(guards, source_dirs())
    for violation in violations:
        print(f"::error::{violation.advisory_id}: {violation.message} ({violation.location})")
    return 1 if violations else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
