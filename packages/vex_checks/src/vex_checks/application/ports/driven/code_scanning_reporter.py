from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import PurePath

from vex_checks.domain.violations import Violation


class CodeScanningReporter(ABC):
    """Reports a check's violations to code scanning, as a SARIF file."""

    @abstractmethod
    def report_claim_problems(
        self, sarif_path: PurePath, rule_id: str, violations: Sequence[Violation], vex_location: str
    ) -> None:
        """One error result under ``rule_id`` per violation, each located at ``vex_location``."""
