from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePath

from vex_checks.application.ports.driven.code_scanning_reporter import CodeScanningReporter
from vex_checks.domain.claim_problem import ClaimProblem


@dataclass(frozen=True)
class WrittenSarif:
    sarif_path: PurePath
    rule_id: str
    claim_problems: tuple[ClaimProblem, ...]
    vex_location: str


class FakeCodeScanningReporter(CodeScanningReporter):
    """Records each report it is asked to write."""

    def __init__(self) -> None:
        self.written_sarifs: list[WrittenSarif] = []

    def report_claim_problems(
        self,
        sarif_path: PurePath,
        rule_id: str,
        claim_problems: Sequence[ClaimProblem],
        vex_location: str,
    ) -> None:
        self.written_sarifs.append(
            WrittenSarif(sarif_path, rule_id, tuple(claim_problems), vex_location)
        )
