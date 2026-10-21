"""CLI gate: assert every image-family VEX claim holds against a built image's SBOM.

Each problem of the check's report prints a GitHub ``::error::`` annotation and exits
non-zero, unless a SARIF output is given: the check then writes them there (always exit zero).
"""

from pathlib import Path

from vex_checks.ports.driving.image_claims_checker import ImageClaimsChecker


def main(
    sbom: Path,
    vex: Path,
    sarif_output: Path | None,
    *,
    image_claims_checker: ImageClaimsChecker,
) -> int:
    report = image_claims_checker.check_image_claims(sbom, vex.resolve(), sarif_output)
    if sarif_output is not None:
        return 0
    for problem in report.problems:
        print(f"::error::{problem.advisory_id}: {problem.message} ({problem.location})")
    return 1 if report.problems else 0
