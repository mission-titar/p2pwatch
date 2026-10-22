"""What a check finds wrong with a claim, its message worded once for the command line and the
SARIF."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimProblem:
    advisory_id: str
    message: str
