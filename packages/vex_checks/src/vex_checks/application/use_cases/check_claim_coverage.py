"""Checks the claims of the VEX files against what backs them: the image premises, the source
rules."""

from collections.abc import Mapping, Sequence
from pathlib import PurePath

from vex_checks.application.ports.driven.source_rule_reader import SourceRuleReader
from vex_checks.application.ports.driven.vex_reader import VexReader
from vex_checks.application.ports.driving.claim_coverage_checker import (
    ClaimCoverageChecker,
    ClaimCoverageReport,
)
from vex_checks.domain.claims import evaluate_claim_coverage, merge_claims
from vex_checks.domain.descriptors import ImagePremise


class CheckClaimCoverage(ClaimCoverageChecker):
    """Over the registry's image premises and the source rules."""

    def __init__(
        self,
        *,
        premises: Mapping[str, ImagePremise],
        vex_paths: Sequence[PurePath],
        vex_reader: VexReader,
        source_rule_reader: SourceRuleReader,
    ) -> None:
        self._premises = premises
        self._vex_paths = vex_paths
        self._vex_reader = vex_reader
        self._source_rule_reader = source_rule_reader

    def check_claim_coverage(self) -> ClaimCoverageReport:
        justifications_by_advisory_id = merge_claims(
            self._vex_reader.read_claims(path) for path in self._vex_paths
        )
        problems = evaluate_claim_coverage(
            justifications_by_advisory_id,
            self._premises.keys(),
            self._source_rule_reader.read_source_rule_ids(),
        )
        return ClaimCoverageReport(problems=tuple(problems))
