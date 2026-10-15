"""CLI gate: assert every source-family VEX claim still holds against our tree.

Exits non-zero (and prints a GitHub ``::error::`` annotation per breach) if any
source premise is contradicted by the shipped source.
"""

import sys

from vex_checks.descriptors import SourcePremise, is_source_premise
from vex_checks.registry import PREMISES
from vex_checks.repo import source_dirs
from vex_checks.source_scan import evaluate_source_premises


def main() -> int:
    premises: dict[str, SourcePremise] = {
        advisory_id: premise
        for advisory_id, premise in PREMISES.items()
        if is_source_premise(premise)
    }
    violations = evaluate_source_premises(premises, source_dirs())
    for violation in violations:
        print(f"::error::{violation.advisory_id}: {violation.message} ({violation.location})")
    return 1 if violations else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
