"""The command line of ``python -m vex_checks``, on the checks."""

from collections.abc import Mapping
from pathlib import Path

from vex_checks.adapters.driven.filesystem_source_rule_reader import FilesystemSourceRuleReader
from vex_checks.adapters.driven.grype_vulnerability_scanner import GrypeVulnerabilityScanner
from vex_checks.adapters.driven.json_sarif_writer import JsonSarifWriter
from vex_checks.adapters.driven.open_vex_reader import OpenVexReader
from vex_checks.adapters.driven.syft_sbom_reader import SyftSbomReader
from vex_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from vex_checks.application.use_cases.check_claim_coverage import CheckClaimCoverage
from vex_checks.application.use_cases.check_image_claims import CheckImageClaims
from vex_checks.application.use_cases.check_stale_claims import CheckStaleClaims
from vex_checks.domain.registry import PREMISES

# Bare, so that the environment's PATH finds it where the workflow installs it.
_GRYPE_EXECUTABLE = "grype"


def build_command_line(
    *, repository_root: Path, env: Mapping[str, str], cwd: Path
) -> ArgparseCommandLine:
    """The command line checking the repository at ``repository_root``, run in the environment
    ``env`` and the directory ``cwd``."""
    vex_reader = OpenVexReader()
    sarif_writer = JsonSarifWriter()
    return ArgparseCommandLine(
        image_claims_checker=CheckImageClaims(
            premises=PREMISES,
            repository_root=repository_root,
            vex_reader=vex_reader,
            sbom_reader=SyftSbomReader(),
            sarif_writer=sarif_writer,
        ),
        stale_claims_checker=CheckStaleClaims(
            repository_root=repository_root,
            vulnerability_scanner=GrypeVulnerabilityScanner(
                grype_executable=_GRYPE_EXECUTABLE, env=env
            ),
            vex_reader=vex_reader,
            sarif_writer=sarif_writer,
        ),
        claim_coverage_checker=CheckClaimCoverage(
            premises=PREMISES,
            vex_paths=tuple(
                repository_root / "security" / f"{image}.vex.openvex.json"
                for image in ("crawler", "amule")
            ),
            vex_reader=vex_reader,
            source_rule_reader=FilesystemSourceRuleReader(
                rules_directory=repository_root / "packages" / "vex_checks" / "ast-grep" / "rules"
            ),
        ),
        cwd=cwd,
    )
