"""CLI gate: enforce a bijection between VEX ``not_affected`` claims and guards.

Every published claim must anchor to exactly one guard, every guard must back a
claim, and each claim's justification must match its guard's family. Any breach
prints a GitHub ``::error::`` annotation and exits non-zero.
"""

import sys

from vex_guards.descriptors import JUSTIFICATION_BY_FAMILY, family
from vex_guards.registry import GUARDS
from vex_guards.repo import vex_files
from vex_guards.vex_io import all_claims


def main() -> int:
    claims = all_claims(list(vex_files().values()))
    problems: list[str] = []
    for advisory_id in set(claims) - set(GUARDS):
        problems.append(f"{advisory_id}: claim has no guard")
    for advisory_id in set(GUARDS) - set(claims):
        problems.append(f"{advisory_id}: guard has no claim")
    for advisory_id in set(claims) & set(GUARDS):
        expected = JUSTIFICATION_BY_FAMILY[family(GUARDS[advisory_id])]
        if claims[advisory_id] != expected:
            problems.append(
                f"{advisory_id}: justification {claims[advisory_id]!r} does not match guard family"
            )
    for problem in problems:
        print(f"::error::{problem}")
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
