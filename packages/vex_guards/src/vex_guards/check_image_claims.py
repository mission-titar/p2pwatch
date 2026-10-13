"""CLI gate: assert every image-family VEX claim holds against a built image's SBOM.

Each image guard asserts a fact about the packages shipped in the image (a
package is absent, or a dpkg or hand-declared one meets a minimum version).
Given a Syft SBOM and the VEX document authored for that image, this checks the
image-family claims only: source-family claims are scoped out. In ``fail`` mode a
breach prints a GitHub ``::error::`` annotation and exits non-zero; in ``sarif``
mode the same breaches are written to ``--output`` as a SARIF report (always exit
zero).
"""

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from vex_guards import repo
from vex_guards.descriptors import ImageGuard, is_image_guard
from vex_guards.registry import GUARDS
from vex_guards.sarif import build_sarif
from vex_guards.sbom import evaluate_image_guards, load_declared_components, load_dpkg_packages
from vex_guards.vex_io import load_claims

_RULE_ID = "unsatisfied-image-claim"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sbom", required=True, help="Syft JSON SBOM of the built image")
    parser.add_argument("--vex", required=True, help="OpenVEX document authored for the image")
    parser.add_argument("--format", choices=("fail", "sarif"), default="fail")
    parser.add_argument("--output", help="SARIF output path (required by --format sarif)")
    args = parser.parse_args(argv)
    if args.format == "sarif" and args.output is None:
        parser.error("--output is required with --format sarif")

    claims = load_claims(Path(args.vex))
    # Iterate GUARDS so the value binds the narrowed loop variable: is_image_guard
    # is a TypeGuard, so ``guard`` types as ImageGuard here with no cast/ignore.
    guards: dict[str, ImageGuard] = {
        advisory_id: guard
        for advisory_id, guard in GUARDS.items()
        if advisory_id in claims and is_image_guard(guard)
    }
    vex_relpath = repo.display_path(Path(args.vex))
    sbom = Path(args.sbom)
    unlocated = evaluate_image_guards(
        guards, load_dpkg_packages(sbom), load_declared_components(sbom)
    )
    violations = [dataclasses.replace(violation, location=vex_relpath) for violation in unlocated]

    if args.format == "sarif":
        Path(args.output).write_text(json.dumps(build_sarif(_RULE_ID, violations, vex_relpath)))
        return 0

    for violation in violations:
        print(f"::error::{violation.advisory_id}: {violation.message} ({violation.location})")
    return 1 if violations else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
