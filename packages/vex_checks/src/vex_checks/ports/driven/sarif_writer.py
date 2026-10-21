from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import PurePath

from vex_checks.domain.violations import Violation


class SarifWriter(ABC):
    """Writes a check's violations as a SARIF report."""

    @abstractmethod
    def write_violations(
        self, sarif_path: PurePath, rule_id: str, violations: Sequence[Violation], vex_relpath: str
    ) -> None:
        """One error result under ``rule_id`` per violation, each located at ``vex_relpath``."""
