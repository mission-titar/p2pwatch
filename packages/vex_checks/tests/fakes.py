from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath

from vex_checks.domain.sbom_components import DeclaredComponent, DpkgPackage
from vex_checks.domain.violations import Violation
from vex_checks.ports.driven.sarif_writer import SarifWriter
from vex_checks.ports.driven.sbom_reader import SbomReader
from vex_checks.ports.driven.source_rule_reader import SourceRuleReader
from vex_checks.ports.driven.vex_reader import VexReader
from vex_checks.ports.driven.vulnerability_scanner import VulnerabilityScanner
from vex_checks.ports.driving.claim_coverage_checker import (
    ClaimCoverageChecker,
    ClaimCoverageProblem,
    ClaimCoverageReport,
)
from vex_checks.ports.driving.image_claims_checker import ImageClaimsChecker, ImageClaimsReport
from vex_checks.ports.driving.stale_claims_checker import StaleClaimsChecker, StaleClaimsReport


class FakeVexReader(VexReader):
    """Reads the claims given for a VEX file, and ``claims`` from any other."""

    def __init__(
        self,
        claims: dict[str, str],
        *,
        claims_by_vex_path: Mapping[PurePath, dict[str, str]] | None = None,
    ) -> None:
        self._claims = claims
        self._claims_by_vex_path = claims_by_vex_path or {}

    def read_claims(self, vex_path: PurePath) -> dict[str, str]:
        return dict(self._claims_by_vex_path.get(vex_path, self._claims))


class FakeSbomReader(SbomReader):
    """Reads the same components from any SBOM."""

    def __init__(
        self,
        *,
        dpkg_packages: Sequence[DpkgPackage] = (),
        declared_components: Sequence[DeclaredComponent] = (),
    ) -> None:
        self._dpkg_packages = dpkg_packages
        self._declared_components = declared_components

    def read_dpkg_packages(self, sbom_path: PurePath) -> list[DpkgPackage]:
        return list(self._dpkg_packages)

    def read_declared_components(self, sbom_path: PurePath) -> list[DeclaredComponent]:
        return list(self._declared_components)


class FakeVulnerabilityScanner(VulnerabilityScanner):
    """Records each SBOM it scans, and finds the same advisories in any."""

    def __init__(self, advisory_ids: set[str]) -> None:
        self._advisory_ids = advisory_ids
        self.scanned_sbom_paths: list[PurePath] = []

    def scan_sbom(self, sbom_path: PurePath) -> set[str]:
        self.scanned_sbom_paths.append(sbom_path)
        return set(self._advisory_ids)


class FakeSourceRuleReader(SourceRuleReader):
    """Reads the source rules' ids it is given."""

    def __init__(self, source_rule_ids: set[str]) -> None:
        self._source_rule_ids = source_rule_ids

    def read_source_rule_ids(self) -> set[str]:
        return set(self._source_rule_ids)


@dataclass(frozen=True)
class WrittenSarif:
    sarif_path: PurePath
    rule_id: str
    violations: tuple[Violation, ...]
    vex_location: str


class FakeSarifWriter(SarifWriter):
    """Records each report it is asked to write."""

    def __init__(self) -> None:
        self.written_sarifs: list[WrittenSarif] = []

    def write_violations(
        self, sarif_path: PurePath, rule_id: str, violations: Sequence[Violation], vex_location: str
    ) -> None:
        self.written_sarifs.append(
            WrittenSarif(sarif_path, rule_id, tuple(violations), vex_location)
        )


@dataclass(frozen=True)
class ImageClaimsCheck:
    sbom_path: PurePath
    vex_path: PurePath
    sarif_path: PurePath | None


class FakeImageClaimsChecker(ImageClaimsChecker):
    """Records each check it is asked for, and answers the same problems to each."""

    def __init__(self, problems: Sequence[Violation] = ()) -> None:
        self._problems = tuple(problems)
        self.checks: list[ImageClaimsCheck] = []

    def check_image_claims(
        self, sbom_path: PurePath, vex_path: PurePath, sarif_path: PurePath | None
    ) -> ImageClaimsReport:
        self.checks.append(ImageClaimsCheck(sbom_path, vex_path, sarif_path))
        return ImageClaimsReport(problems=self._problems)


@dataclass(frozen=True)
class StaleClaimsCheck:
    sbom_path: PurePath
    vex_path: PurePath
    sarif_path: PurePath | None


class FakeStaleClaimsChecker(StaleClaimsChecker):
    """Records each check it is asked for, and answers the same problems to each."""

    def __init__(self, problems: Sequence[Violation] = ()) -> None:
        self._problems = tuple(problems)
        self.checks: list[StaleClaimsCheck] = []

    def check_stale_claims(
        self, sbom_path: PurePath, vex_path: PurePath, sarif_path: PurePath | None
    ) -> StaleClaimsReport:
        self.checks.append(StaleClaimsCheck(sbom_path, vex_path, sarif_path))
        return StaleClaimsReport(problems=self._problems)


class FakeClaimCoverageChecker(ClaimCoverageChecker):
    """Counts the checks it is asked for, and answers the same problems to each."""

    def __init__(self, problems: Sequence[ClaimCoverageProblem] = ()) -> None:
        self._problems = tuple(problems)
        self.check_count = 0

    def check_claim_coverage(self) -> ClaimCoverageReport:
        self.check_count += 1
        return ClaimCoverageReport(problems=self._problems)
