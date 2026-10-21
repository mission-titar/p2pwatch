import pytest

from vex_checks.domain.claims import merge_claims


def test_merge_claims_unites_the_claims_of_each_vex() -> None:
    merged = merge_claims(
        [
            {"CVE-1": "vulnerable_code_not_present"},
            {"CVE-2": "vulnerable_code_not_in_execute_path"},
        ]
    )
    assert merged == {
        "CVE-1": "vulnerable_code_not_present",
        "CVE-2": "vulnerable_code_not_in_execute_path",
    }


def test_merge_claims_keeps_one_claim_two_vex_agree_on() -> None:
    claims = {"CVE-SHARED": "vulnerable_code_not_present"}
    assert merge_claims([claims, claims]) == claims


def test_merge_claims_refuses_two_justifications_of_one_advisory() -> None:
    with pytest.raises(ValueError, match="CVE-SHARED has conflicting justifications"):
        merge_claims(
            [
                {"CVE-SHARED": "vulnerable_code_not_present"},
                {"CVE-SHARED": "vulnerable_code_not_in_execute_path"},
            ]
        )
