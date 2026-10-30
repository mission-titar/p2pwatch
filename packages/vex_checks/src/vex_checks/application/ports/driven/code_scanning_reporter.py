from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import PurePath

from vex_checks.domain.claim_problem import ClaimProblem


class CodeScanningReporter(ABC):
    """Reports a check's claim problems to code scanning, as a SARIF file."""

    @abstractmethod
    def report_claim_problems(
        self,
        sarif_path: PurePath,
        *,
        rule_id: str,
        claim_problems: Sequence[ClaimProblem],
        vex_location: str,
    ) -> None:
        """One error result under ``rule_id`` per problem, each located at ``vex_location``."""
