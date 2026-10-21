"""CLI gate: flag VEX ``not_affected`` claims Grype no longer reports.

A ``not_affected`` claim asserts a fact about a live vulnerability. Once Grype
stops reporting that vulnerability for the image, the claim has outlived its
subject and should be pruned. Given a Syft SBOM (scanned by Grype) and the VEX
document authored for that image, this lists every claimed advisory that Grype no
longer reports. A stale entry prints a GitHub ``::error::`` annotation and exits
non-zero, unless a SARIF output is given: the same entries are then written there as
a SARIF report (always exit zero).
"""

from pathlib import Path

from vex_checks.adapters.driven import repo
from vex_checks.adapters.driven.grype import GrypeRunner
from vex_checks.domain.violations import Violation
from vex_checks.ports.driven.sarif_writer import SarifWriter
from vex_checks.ports.driven.vex_reader import VexReader

_RULE_ID = "stale-vex-entry"


def main(
    sbom: Path,
    vex: Path,
    sarif_output: Path | None,
    *,
    runner: GrypeRunner,
    vex_reader: VexReader,
    sarif_writer: SarifWriter,
) -> int:
    reported = runner.run(sbom)
    vex_relpath = repo.display_path(vex)
    stale = [
        Violation(advisory_id, "no longer reported by Grype", vex_relpath)
        for advisory_id in vex_reader.read_claims(vex)
        if advisory_id not in reported
    ]

    if sarif_output is not None:
        sarif_writer.write_violations(sarif_output, _RULE_ID, stale, vex_relpath)
        return 0

    for violation in stale:
        print(f"::error::{violation.advisory_id}: {violation.message} ({violation.location})")
    return 1 if stale else 0
