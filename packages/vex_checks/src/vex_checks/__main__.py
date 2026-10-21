"""``python -m vex_checks``: hands the checks to the command line."""

import functools
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from vex_checks.adapters.driven import repo
from vex_checks.adapters.driven.grype_vulnerability_scanner import GrypeVulnerabilityScanner
from vex_checks.adapters.driven.json_sarif_writer import JsonSarifWriter
from vex_checks.adapters.driven.json_vex_reader import JsonVexReader
from vex_checks.adapters.driven.syft_sbom_reader import SyftSbomReader
from vex_checks.adapters.driving import check_claim_coverage, check_source_claims
from vex_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from vex_checks.application.check_image_claims import CheckImageClaims
from vex_checks.application.check_stale_claims import CheckStaleClaims
from vex_checks.domain.registry import PREMISES

# Bare, so that the environment's PATH finds it where the workflow installs it.
_GRYPE_EXECUTABLE = "grype"


def main(argv: Sequence[str], env: Mapping[str, str], cwd: Path) -> int:
    """Runs the subcommand ``argv`` names in the environment ``env`` and the directory ``cwd``,
    returns its exit code."""
    repo_root = repo.repo_root()
    vex_reader = JsonVexReader()
    sarif_writer = JsonSarifWriter()
    command_line = ArgparseCommandLine(
        image_claims_checker=CheckImageClaims(
            premises=PREMISES,
            repo_root=repo_root,
            vex_reader=vex_reader,
            sbom_reader=SyftSbomReader(),
            sarif_writer=sarif_writer,
        ),
        stale_claims_checker=CheckStaleClaims(
            repo_root=repo_root,
            vulnerability_scanner=GrypeVulnerabilityScanner(
                grype_executable=_GRYPE_EXECUTABLE, env=env
            ),
            vex_reader=vex_reader,
            sarif_writer=sarif_writer,
        ),
        check_source_claims=check_source_claims.main,
        check_claim_coverage=functools.partial(check_claim_coverage.main, vex_reader=vex_reader),
        cwd=cwd,
    )
    return command_line.run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:], os.environ, Path.cwd()))
