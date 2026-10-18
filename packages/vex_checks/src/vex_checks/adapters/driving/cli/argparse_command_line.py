"""The command line: parses a subcommand, calls its check, returns the exit code."""

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

# Over a built image's SBOM and its VEX; given a SARIF output, it writes there instead of failing.
type ImageCheck = Callable[[Path, Path, Path | None], int]


def _add_image_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--sbom", type=Path, required=True, help="Syft JSON SBOM of the built image"
    )
    parser.add_argument(
        "--vex", type=Path, required=True, help="OpenVEX document authored for the image"
    )
    parser.add_argument("--format", choices=("fail", "sarif"), default="fail")
    parser.add_argument(
        "--output", type=Path, help="SARIF output path (required by --format sarif)"
    )


def _run_image_check(
    check: ImageCheck, parser: argparse.ArgumentParser, args: argparse.Namespace
) -> int:
    if args.format == "sarif" and args.output is None:
        parser.error("--output is required with --format sarif")
    return check(args.sbom, args.vex, args.output if args.format == "sarif" else None)


class ArgparseCommandLine:
    """``image-claims``, ``stale-claims``, ``source-claims``, ``claim-coverage``: one check each."""

    def __init__(
        self,
        *,
        check_image_claims: ImageCheck,
        check_stale_claims: ImageCheck,
        check_source_claims: Callable[[], int],
        check_claim_coverage: Callable[[], int],
    ) -> None:
        self._check_image_claims = check_image_claims
        self._check_stale_claims = check_stale_claims
        self._check_source_claims = check_source_claims
        self._check_claim_coverage = check_claim_coverage

    def run(self, argv: Sequence[str] | None = None) -> int:
        """Runs the subcommand ``argv`` names (``sys.argv`` if ``None``), returns its exit code."""
        parser = argparse.ArgumentParser(
            prog="vex_checks", description="keep our OpenVEX not_affected claims honest"
        )
        subparsers = parser.add_subparsers(dest="command", required=True)
        image_claims = subparsers.add_parser(
            "image-claims", help="check the image-family claims against the image's SBOM"
        )
        _add_image_options(image_claims)
        stale_claims = subparsers.add_parser(
            "stale-claims", help="flag the claims Grype no longer reports for the image"
        )
        _add_image_options(stale_claims)
        subparsers.add_parser(
            "source-claims", help="check the source-family claims against our tree"
        )
        subparsers.add_parser(
            "claim-coverage", help="check that every claim maps to one premise, and back"
        )
        args = parser.parse_args(argv)
        if args.command == "image-claims":
            return _run_image_check(self._check_image_claims, image_claims, args)
        if args.command == "stale-claims":
            return _run_image_check(self._check_stale_claims, stale_claims, args)
        if args.command == "source-claims":
            return self._check_source_claims()
        return self._check_claim_coverage()
