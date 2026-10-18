"""CLI gate: assert every source-family VEX claim still holds against our tree.

Exits non-zero (and prints a GitHub ``::error::`` annotation per breach) if any
source premise is contradicted by the shipped source.
"""

from vex_checks.adapters.driven.repo import source_dirs
from vex_checks.adapters.driven.source_scan import evaluate_source_premises
from vex_checks.domain.descriptors import SourcePremise, is_source_premise
from vex_checks.domain.registry import PREMISES


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
