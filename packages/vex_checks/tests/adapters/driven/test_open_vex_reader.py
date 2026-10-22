import json
from pathlib import Path

import pytest

from vex_checks.adapters.driven.open_vex_reader import OpenVexReader


def test_read_claims_keeps_the_not_affected_statements_only(tmp_path: Path) -> None:
    vex_path = tmp_path / "x.vex.openvex.json"
    not_affected = {
        "vulnerability": {"name": "CVE-1"},
        "status": "not_affected",
        "justification": "vulnerable_code_not_present",
    }
    affected = {"vulnerability": {"name": "CVE-2"}, "status": "affected"}
    vex_path.write_text(json.dumps({"statements": [not_affected, affected]}))

    assert OpenVexReader().read_claims(vex_path) == {"CVE-1": "vulnerable_code_not_present"}


def test_read_claims_of_an_absent_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        OpenVexReader().read_claims(tmp_path / "absent.vex.openvex.json")
