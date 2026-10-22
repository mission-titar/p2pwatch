import json
from collections.abc import Sequence
from pathlib import Path, PurePath

from vex_checks.application.ports.driven.code_scanning_reporter import CodeScanningReporter
from vex_checks.domain.violations import Violation


class FilesystemCodeScanningReporter(CodeScanningReporter):
    """A SARIF 2.1.0 report as a JSON file at the path each call is given."""

    def report_claim_problems(
        self, sarif_path: PurePath, rule_id: str, violations: Sequence[Violation], vex_location: str
    ) -> None:
        Path(sarif_path).write_text(json.dumps(_sarif(rule_id, violations, vex_location)))


def _sarif(rule_id: str, violations: Sequence[Violation], vex_location: str) -> dict[str, object]:
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "vex-consistency",
                        "rules": [{"id": rule_id}],
                    }
                },
                "results": [
                    {
                        "ruleId": rule_id,
                        "level": "error",
                        "message": {"text": f"{violation.advisory_id}: {violation.message}"},
                        "locations": [
                            {"physicalLocation": {"artifactLocation": {"uri": vex_location}}}
                        ],
                    }
                    for violation in violations
                ],
            }
        ],
    }
