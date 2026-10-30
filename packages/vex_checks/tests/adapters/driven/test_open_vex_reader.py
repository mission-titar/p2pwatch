import json
import re
from pathlib import Path

import pytest

from vex_checks.adapters.driven.open_vex_reader import OpenVexReader
from vex_checks.domain.broken_input_error import BrokenInputError


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


def test_read_claims_of_an_absent_file_raises_a_broken_input_naming_it(tmp_path: Path) -> None:
    vex_path = tmp_path / "absent.vex.openvex.json"

    with pytest.raises(BrokenInputError, match=f"^{re.escape(str(vex_path))}: no such file$"):
        OpenVexReader().read_claims(vex_path)


def test_read_claims_of_a_directory_raises_a_broken_input_naming_it(tmp_path: Path) -> None:
    with pytest.raises(BrokenInputError, match=f"^{re.escape(str(tmp_path))}: Is a directory$"):
        OpenVexReader().read_claims(tmp_path)


def test_read_claims_of_a_file_not_in_utf_8_raises_a_broken_input_naming_it(
    tmp_path: Path,
) -> None:
    vex_path = tmp_path / "x.vex.openvex.json"
    vex_path.write_bytes(b'{"statements": "\xe9"}')

    with pytest.raises(BrokenInputError, match=f"^{re.escape(str(vex_path))}: not UTF-8$"):
        OpenVexReader().read_claims(vex_path)


def test_read_claims_of_a_file_not_in_json_raises_a_broken_input_naming_it(
    tmp_path: Path,
) -> None:
    vex_path = tmp_path / "x.vex.openvex.json"
    vex_path.write_text("{")

    with pytest.raises(BrokenInputError, match=f"^{re.escape(str(vex_path))}: not JSON$"):
        OpenVexReader().read_claims(vex_path)


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"statements": 3},
        {"statements": ["CVE-1"]},
        {"statements": [{"status": "not_affected"}]},
    ],
    ids=["no-statements", "statements-not-a-list", "statement-not-an-object", "no-vulnerability"],
)
def test_read_claims_of_a_json_not_an_openvex_document_raises_a_broken_input_naming_it(
    *, document: object, tmp_path: Path
) -> None:
    vex_path = tmp_path / "x.vex.openvex.json"
    vex_path.write_text(json.dumps(document))

    with pytest.raises(
        BrokenInputError, match=f"^{re.escape(str(vex_path))}: not an OpenVEX document$"
    ):
        OpenVexReader().read_claims(vex_path)
