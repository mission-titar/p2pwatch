import json
from pathlib import Path
from typing import cast

from vex_checks.adapters.driven.json_sarif_writer import JsonSarifWriter
from vex_checks.domain.violations import Violation

_RULE_ID = "vex-consistency-tarfile"
_VEX_RELPATH = "security/crawler.vex.openvex.json"


def test_empty_violations_yields_valid_sarif_with_no_results(tmp_path: Path) -> None:
    sarif_path = tmp_path / "out.sarif"

    JsonSarifWriter().write_violations(sarif_path, _RULE_ID, [], _VEX_RELPATH)

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


def test_one_violation_yields_one_error_result_pointing_at_the_vex_file(tmp_path: Path) -> None:
    sarif_path = tmp_path / "out.sarif"
    violation = Violation(
        advisory_id="CVE-2026-11940",
        message="tarfile is imported at src/p2pwatch/foo.py",
        location="packages/crawler/src/p2pwatch/foo.py",
    )

    JsonSarifWriter().write_violations(sarif_path, _RULE_ID, [violation], _VEX_RELPATH)

    sarif = json.loads(sarif_path.read_text())
    runs = cast(list[dict[str, object]], sarif["runs"])
    results = cast(list[dict[str, object]], runs[0]["results"])
    assert len(results) == 1
    sarif_result = results[0]

    assert sarif_result["ruleId"] == _RULE_ID
    assert sarif_result["level"] == "error"

    message = cast(dict[str, object], sarif_result["message"])
    text = cast(str, message["text"])
    assert violation.advisory_id in text

    locations = cast(list[dict[str, object]], sarif_result["locations"])
    physical = cast(dict[str, object], locations[0]["physicalLocation"])
    artifact = cast(dict[str, object], physical["artifactLocation"])
    assert artifact["uri"] == _VEX_RELPATH
