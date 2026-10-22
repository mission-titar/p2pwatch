"""Checks the claims of the VEX files against what backs them: the image premises, the source
rules."""

from collections.abc import Mapping, Sequence
from pathlib import PurePath

from vex_checks.application.ports.driven.source_rule_reader import SourceRuleReader
from vex_checks.application.ports.driven.vex_reader import VexReader
from vex_checks.application.ports.driving.claim_coverage_checker import (
    ClaimCoverageChecker,
    ClaimCoverageProblem,
    ClaimCoverageReport,
)
from vex_checks.domain.claims import (
    IMAGE_PREMISE_JUSTIFICATION,
    SOURCE_RULE_JUSTIFICATION,
    merge_claims,
)
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
        claimed_ids = justifications_by_advisory_id.keys()
        image_premise_ids = set(self._premises)
        source_rule_ids = self._source_rule_reader.read_source_rule_ids()
        backed_twice = image_premise_ids & source_rule_ids
        justification_by_backed_id = {
            **dict.fromkeys(image_premise_ids, IMAGE_PREMISE_JUSTIFICATION),
            **dict.fromkeys(source_rule_ids, SOURCE_RULE_JUSTIFICATION),
        }
        problems = [
            *(
                ClaimCoverageProblem(advisory_id, "justified differently across VEX files")
                for advisory_id, justifications in justifications_by_advisory_id.items()
                if len(justifications) > 1
            ),
            *(
                ClaimCoverageProblem(advisory_id, "has both an image premise and a source rule")
                for advisory_id in backed_twice
            ),
            *(
                ClaimCoverageProblem(advisory_id, "claim has no premise or source rule")
                for advisory_id in claimed_ids - justification_by_backed_id.keys()
            ),
            *(
                ClaimCoverageProblem(advisory_id, "premise has no claim")
                for advisory_id in image_premise_ids - claimed_ids
            ),
            *(
                ClaimCoverageProblem(advisory_id, "source rule has no claim")
                for advisory_id in source_rule_ids - claimed_ids
            ),
            *(
                ClaimCoverageProblem(
                    advisory_id,
                    f"justification {justification!r}"
                    f" is not {justification_by_backed_id[advisory_id]!r}",
                )
                for advisory_id in claimed_ids & justification_by_backed_id.keys() - backed_twice
                for justification in justifications_by_advisory_id[advisory_id]
                if justification != justification_by_backed_id[advisory_id]
            ),
        ]
        return ClaimCoverageReport(
            problems=tuple(
                sorted(problems, key=lambda problem: (problem.advisory_id, problem.message))
            )
        )
