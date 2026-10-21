import pytest

from tests.fakes import FakeVexReader
from vex_checks.adapters.driven.json_vex_reader import JsonVexReader
from vex_checks.adapters.driving import check_claim_coverage
from vex_checks.domain.descriptors import DpkgPackageAbsent, ModuleNotImported


def test_main_returns_zero_on_the_real_registry_and_vex() -> None:
    # The TDD payoff: Task 3's authored VEX and Task 2's registry were built to
    # agree, so the bijection check must be green with no injection at all.
    assert check_claim_coverage.main(vex_reader=JsonVexReader()) == 0


def test_claim_without_a_premise_fails_and_names_the_cve(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vex_reader = FakeVexReader({"CVE-9999": "vulnerable_code_not_in_execute_path"})
    monkeypatch.setattr(check_claim_coverage, "PREMISES", {})

    assert check_claim_coverage.main(vex_reader=vex_reader) == 1
    out = capsys.readouterr().out
    assert "::error::CVE-9999: claim has no premise" in out


def test_premise_without_a_claim_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        check_claim_coverage,
        "PREMISES",
        {"CVE-8888": ModuleNotImported("tarfile")},
    )

    assert check_claim_coverage.main(vex_reader=FakeVexReader({})) == 1
    out = capsys.readouterr().out
    assert "::error::CVE-8888: premise has no claim" in out


def test_justification_that_mismatches_the_premise_family_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # An image premise expects ``vulnerable_code_not_present``; pairing it with the
    # source justification is the family mismatch the bijection check rejects.
    vex_reader = FakeVexReader({"CVE-7777": "vulnerable_code_not_in_execute_path"})
    monkeypatch.setattr(
        check_claim_coverage,
        "PREMISES",
        {"CVE-7777": DpkgPackageAbsent("nghttp2")},
    )

    assert check_claim_coverage.main(vex_reader=vex_reader) == 1
    out = capsys.readouterr().out
    assert "::error::CVE-7777: justification" in out
    assert "does not match premise family" in out
