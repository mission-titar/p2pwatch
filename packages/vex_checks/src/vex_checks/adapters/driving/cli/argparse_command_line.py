"""The command line: parses a subcommand, calls its check, returns the exit code."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import PurePath
from typing import Protocol

from vex_checks.application.ports.driving.applied_claims_checker import AppliedClaimsChecker
from vex_checks.application.ports.driving.claim_coverage_checker import ClaimCoverageChecker
from vex_checks.application.ports.driving.image_claims_checker import ImageClaimsChecker
from vex_checks.domain.broken_input_error import BrokenInputError
from vex_checks.domain.claim_problem import ClaimProblem


class CwdResolver(Protocol):
    def __call__(self, path: str, /) -> PurePath: ...


def _add_image_options(parser: argparse.ArgumentParser, under_cwd: CwdResolver) -> None:
    parser.add_argument(
        "--sbom", type=under_cwd, required=True, help="Syft JSON SBOM of the built image"
    )
    parser.add_argument(
        "--vex", type=under_cwd, required=True, help="OpenVEX document authored for the image"
    )
    parser.add_argument(
        "--sarif", type=under_cwd, help="write the problems as SARIF there instead of printing them"
    )


def _print_problems(
    problems: Sequence[ClaimProblem], vex_location: str, sarif_output: PurePath | None
) -> int:
    """Each problem a GitHub ``::error::`` line and exit 1, or, written as SARIF, exit 0."""
    if sarif_output is not None:
        return 0
    for problem in problems:
        print(f"::error::{problem.advisory_id}: {problem.message} ({vex_location})")
    return 1 if problems else 0


class ArgparseCommandLine:
    """``image-claims``, ``applied-claims`` and ``claim-coverage`` over their checkers. A relative
    path is taken under ``cwd``."""

    def __init__(
        self,
        *,
        image_claims_checker: ImageClaimsChecker,
        applied_claims_checker: AppliedClaimsChecker,
        claim_coverage_checker: ClaimCoverageChecker,
        cwd: PurePath,
    ) -> None:
        self._image_claims_checker = image_claims_checker
        self._applied_claims_checker = applied_claims_checker
        self._claim_coverage_checker = claim_coverage_checker
        self._cwd = cwd

    def run(self, argv: Sequence[str]) -> int:
        """Runs the subcommand ``argv`` names, returns its exit code."""
        parser = argparse.ArgumentParser(
            prog="vex_checks", description="keep our OpenVEX not_affected claims honest"
        )
        subparsers = parser.add_subparsers(dest="command", required=True)
        image_claims = subparsers.add_parser(
            "image-claims", help="check the image claims against the image's SBOM"
        )
        _add_image_options(image_claims, self._under_cwd)
        applied_claims = subparsers.add_parser(
            "applied-claims", help="flag the claims Grype does not report or apply for the image"
        )
        _add_image_options(applied_claims, self._under_cwd)
        subparsers.add_parser(
            "claim-coverage",
            help="check that every claim maps to one image premise or source rule, and back",
        )
        args = parser.parse_args(argv)
        try:
            if args.command == "image-claims":
                return self._check_image_claims(args.sbom, args.vex, args.sarif)
            if args.command == "applied-claims":
                return self._check_applied_claims(args.sbom, args.vex, args.sarif)
            return self._check_claim_coverage()
        except BrokenInputError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1

    def _check_image_claims(
        self, sbom: PurePath, vex: PurePath, sarif_output: PurePath | None
    ) -> int:
        report = self._image_claims_checker.check_image_claims(sbom, vex, sarif_output)
        return _print_problems(report.problems, report.vex_location, sarif_output)

    def _check_applied_claims(
        self, sbom: PurePath, vex: PurePath, sarif_output: PurePath | None
    ) -> int:
        report = self._applied_claims_checker.check_applied_claims(sbom, vex, sarif_output)
        return _print_problems(report.problems, report.vex_location, sarif_output)

    def _check_claim_coverage(self) -> int:
        report = self._claim_coverage_checker.check_claim_coverage()
        for problem in report.problems:
            print(f"::error::{problem.advisory_id}: {problem.message}")
        return 1 if report.problems else 0

    def _under_cwd(self, path: str) -> PurePath:
        """``path`` under ``cwd``, or as it is when absolute."""
        return self._cwd / path
