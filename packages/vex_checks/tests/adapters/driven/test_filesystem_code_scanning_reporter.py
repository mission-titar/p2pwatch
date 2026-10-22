import json
from pathlib import Path
from typing import cast

from vex_checks.adapters.driven.filesystem_code_scanning_reporter import (
    FilesystemCodeScanningReporter,
)
from vex_checks.domain.claim_problem import ClaimProblem

_RULE_ID = "vex-consistency-tarfile"
_VEX_RELPATH = "security/crawler.vex.openvex.json"


def test_no_claim_problem_yields_valid_sarif_with_no_results(tmp_path: Path) -> None:
    sarif_path = tmp_path / "out.sarif"

    FilesystemCodeScanningReporter().report_claim_problems(sarif_path, _RULE_ID, [], _VEX_RELPATH)

    sarif = json.loads(sarif_path.read_text())
    assert sarif["$schema"] == "https://json.schemastore.org/sarif-2.1.0.json"
    assert sarif["version"] == "2.1.0"

    runs = cast(list[dict[str, object]], sarif["runs"])
    assert len(runs) == 1
    run = runs[0]

    tool = cast(dict[str, object], run["tool"])
    driver = cast(dict[str, object], tool["driver"])
    assert driver["name"] == "vex-consistency"

    rules = cast(list[dict[str, object]], driver["rules"])
    assert any(rule["id"] == _RULE_ID for rule in rules)

    assert run["results"] == []


def test_one_claim_problem_yields_one_error_result_pointing_at_the_vex_file(
    tmp_path: Path,
) -> None:
    sarif_path = tmp_path / "out.sarif"
    claim_problem = ClaimProblem("CVE-2026-11940", "no longer reported by Grype")

    FilesystemCodeScanningReporter().report_claim_problems(
        sarif_path, _RULE_ID, [claim_problem], _VEX_RELPATH
    )

    sarif = json.loads(sarif_path.read_text())
    runs = cast(list[dict[str, object]], sarif["runs"])
    results = cast(list[dict[str, object]], runs[0]["results"])
    assert len(results) == 1
    sarif_result = results[0]

    assert sarif_result["ruleId"] == _RULE_ID
    assert sarif_result["level"] == "error"

    message = cast(dict[str, object], sarif_result["message"])
    assert message["text"] == "CVE-2026-11940: no longer reported by Grype"

    locations = cast(list[dict[str, object]], sarif_result["locations"])
    physical = cast(dict[str, object], locations[0]["physicalLocation"])
    artifact = cast(dict[str, object], physical["artifactLocation"])
    assert artifact["uri"] == _VEX_RELPATH
