"""The command line: parses a subcommand, calls its check, returns the exit code."""

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

from vex_checks.application.ports.driving.claim_coverage_checker import ClaimCoverageChecker
from vex_checks.application.ports.driving.image_claims_checker import ImageClaimsChecker
from vex_checks.application.ports.driving.stale_claims_checker import StaleClaimsChecker
from vex_checks.domain.violations import Violation


def _add_image_options(
    parser: argparse.ArgumentParser,
    under_cwd: Callable[[str], Path],
    resolved_under_cwd: Callable[[str], Path],
) -> None:
    parser.add_argument(
        "--sbom", type=under_cwd, required=True, help="Syft JSON SBOM of the built image"
    )
    # Resolved, so that a VEX of the repository is located relative to its root.
    parser.add_argument(
        "--vex",
        type=resolved_under_cwd,
        required=True,
        help="OpenVEX document authored for the image",
    )
    parser.add_argument("--format", choices=("fail", "sarif"), default="fail")
    parser.add_argument(
        "--output", type=under_cwd, help="SARIF output path (required by --format sarif)"
    )


def _sarif_output(parser: argparse.ArgumentParser, args: argparse.Namespace) -> Path | None:
    if args.format == "sarif" and args.output is None:
        parser.error("--output is required with --format sarif")
    return args.output if args.format == "sarif" else None


def _print_problems(problems: Sequence[Violation], sarif_output: Path | None) -> int:
    """Each problem a GitHub ``::error::`` line and exit 1, or, written as SARIF, exit 0."""
    if sarif_output is not None:
        return 0
    for problem in problems:
        print(f"::error::{problem.advisory_id}: {problem.message} ({problem.location})")
    return 1 if problems else 0


class ArgparseCommandLine:
    """``image-claims``, ``stale-claims`` and ``claim-coverage`` over their checkers. A relative
    path is taken under ``cwd``."""

    def __init__(
        self,
        *,
        image_claims_checker: ImageClaimsChecker,
        stale_claims_checker: StaleClaimsChecker,
        claim_coverage_checker: ClaimCoverageChecker,
        cwd: Path,
    ) -> None:
        self._image_claims_checker = image_claims_checker
        self._stale_claims_checker = stale_claims_checker
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
        _add_image_options(image_claims, self._under_cwd, self._resolved_under_cwd)
        stale_claims = subparsers.add_parser(
            "stale-claims", help="flag the claims Grype no longer reports for the image"
        )
        _add_image_options(stale_claims, self._under_cwd, self._resolved_under_cwd)
        subparsers.add_parser(
            "claim-coverage",
            help="check that every claim maps to one image premise or source rule, and back",
        )
        args = parser.parse_args(argv)
        if args.command == "image-claims":
            return self._check_image_claims(args.sbom, args.vex, _sarif_output(image_claims, args))
        if args.command == "stale-claims":
            return self._check_stale_claims(args.sbom, args.vex, _sarif_output(stale_claims, args))
        return self._check_claim_coverage()

    def _check_image_claims(self, sbom: Path, vex: Path, sarif_output: Path | None) -> int:
        report = self._image_claims_checker.check_image_claims(sbom, vex, sarif_output)
        return _print_problems(report.problems, sarif_output)

    def _check_stale_claims(self, sbom: Path, vex: Path, sarif_output: Path | None) -> int:
        report = self._stale_claims_checker.check_stale_claims(sbom, vex, sarif_output)
        return _print_problems(report.problems, sarif_output)

    def _check_claim_coverage(self) -> int:
        report = self._claim_coverage_checker.check_claim_coverage()
        for problem in report.problems:
            print(f"::error::{problem.advisory_id}: {problem.message}")
        return 1 if report.problems else 0

    def _under_cwd(self, path: str) -> Path:
        """``path`` under ``cwd``, or as it is when absolute."""
        return self._cwd / path

    def _resolved_under_cwd(self, path: str) -> Path:
        return self._under_cwd(path).resolve()
