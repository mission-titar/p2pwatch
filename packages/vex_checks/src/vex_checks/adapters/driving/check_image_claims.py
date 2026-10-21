"""CLI gate: assert every image-family VEX claim holds against a built image's SBOM.

Each image premise asserts a fact about the packages shipped in the image (a
package is absent, or a dpkg or hand-declared one meets a minimum version).
Given a Syft SBOM and the VEX document authored for that image, this checks the
image-family claims only: source-family claims are scoped out. A breach prints a
GitHub ``::error::`` annotation and exits non-zero, unless a SARIF output is given:
the same breaches are then written there as a SARIF report (always exit zero).
"""

import dataclasses
from pathlib import Path

from vex_checks.adapters.driven import repo
from vex_checks.adapters.driven.sbom import evaluate_image_premises
from vex_checks.domain.descriptors import ImagePremise, is_image_premise
from vex_checks.domain.registry import PREMISES
from vex_checks.ports.driven.sarif_writer import SarifWriter
from vex_checks.ports.driven.sbom_reader import SbomReader
from vex_checks.ports.driven.vex_reader import VexReader

_RULE_ID = "unsatisfied-image-claim"


def main(
    sbom: Path,
    vex: Path,
    sarif_output: Path | None,
    *,
    vex_reader: VexReader,
    sbom_reader: SbomReader,
    sarif_writer: SarifWriter,
) -> int:
    claims = vex_reader.read_claims(vex)
    # Iterate PREMISES so the value binds the narrowed loop variable: is_image_premise
    # is a TypeIs, so ``premise`` types as ImagePremise here with no cast/ignore.
    premises: dict[str, ImagePremise] = {
        advisory_id: premise
        for advisory_id, premise in PREMISES.items()
        if advisory_id in claims and is_image_premise(premise)
    }
    vex_relpath = repo.display_path(vex)
    unlocated = evaluate_image_premises(
        premises, sbom_reader.read_dpkg_packages(sbom), sbom_reader.read_declared_components(sbom)
    )
    violations = [dataclasses.replace(violation, location=vex_relpath) for violation in unlocated]

    if sarif_output is not None:
        sarif_writer.write_violations(sarif_output, _RULE_ID, violations, vex_relpath)
        return 0

    for violation in violations:
        print(f"::error::{violation.advisory_id}: {violation.message} ({violation.location})")
    return 1 if violations else 0
