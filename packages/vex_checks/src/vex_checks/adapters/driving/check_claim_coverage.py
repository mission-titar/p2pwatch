"""CLI gate: the claims' coverage, each problem a GitHub ``::error::`` annotation."""

from vex_checks.ports.driving.claim_coverage_checker import ClaimCoverageChecker


def main(*, claim_coverage_checker: ClaimCoverageChecker) -> int:
    report = claim_coverage_checker.check_claim_coverage()
    for problem in report.problems:
        print(f"::error::{problem.advisory_id}: {problem.message}")
    return 1 if report.problems else 0
