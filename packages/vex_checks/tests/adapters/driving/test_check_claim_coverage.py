import pytest

from tests.fakes import FakeClaimCoverageChecker
from vex_checks.adapters.driving import check_claim_coverage
from vex_checks.ports.driving.claim_coverage_checker import ClaimCoverageProblem


def test_main_prints_each_problem_as_an_error_and_returns_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    checker = FakeClaimCoverageChecker(
        [
            ClaimCoverageProblem("CVE-A", "claim has no premise or source rule"),
            ClaimCoverageProblem("CVE-B", "premise has no claim"),
        ]
    )

    assert check_claim_coverage.main(claim_coverage_checker=checker) == 1

    assert capsys.readouterr().out == (
        "::error::CVE-A: claim has no premise or source rule\n"
        "::error::CVE-B: premise has no claim\n"
    )


def test_main_with_no_problem_prints_nothing_and_returns_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    checker = FakeClaimCoverageChecker()

    assert check_claim_coverage.main(claim_coverage_checker=checker) == 0

    assert capsys.readouterr().out == ""
