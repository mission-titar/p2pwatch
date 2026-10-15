"""CLI gate: enforce a bijection between VEX ``not_affected`` claims and premises.

Every published claim must anchor to exactly one premise, every premise must back a
claim, and each claim's justification must match its premise's family. Any breach
prints a GitHub ``::error::`` annotation and exits non-zero.
"""

import sys

from vex_checks.descriptors import JUSTIFICATION_BY_FAMILY, family
from vex_checks.registry import PREMISES
from vex_checks.repo import vex_files
from vex_checks.vex_io import all_claims


def main() -> int:
    claims = all_claims(list(vex_files().values()))
    problems: list[str] = []
    for advisory_id in set(claims) - set(PREMISES):
        problems.append(f"{advisory_id}: claim has no premise")
    for advisory_id in set(PREMISES) - set(claims):
        problems.append(f"{advisory_id}: premise has no claim")
    for advisory_id in set(claims) & set(PREMISES):
        expected = JUSTIFICATION_BY_FAMILY[family(PREMISES[advisory_id])]
        if claims[advisory_id] != expected:
            problems.append(
                f"{advisory_id}: justification {claims[advisory_id]!r}"
                " does not match premise family"
            )
    for problem in problems:
        print(f"::error::{problem}")
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
