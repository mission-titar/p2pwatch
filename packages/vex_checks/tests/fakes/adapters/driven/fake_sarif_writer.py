from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePath

from vex_checks.application.ports.driven.sarif_writer import SarifWriter
from vex_checks.domain.violations import Violation


@dataclass(frozen=True)
class WrittenSarif:
    sarif_path: PurePath
    rule_id: str
    violations: tuple[Violation, ...]
    vex_location: str


class FakeSarifWriter(SarifWriter):
    """Records each report it is asked to write."""

    def __init__(self) -> None:
        self.written_sarifs: list[WrittenSarif] = []

    def write_violations(
        self, sarif_path: PurePath, rule_id: str, violations: Sequence[Violation], vex_location: str
    ) -> None:
        self.written_sarifs.append(
            WrittenSarif(sarif_path, rule_id, tuple(violations), vex_location)
        )
