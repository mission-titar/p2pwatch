"""Checks the claims of the VEX files against what backs them: the image premises, the source
rules."""

from collections.abc import Mapping, Sequence
from pathlib import PurePath

from vex_checks.domain.claims import merge_claims
from vex_checks.domain.descriptors import JUSTIFICATION_BY_FAMILY, Premise, is_image_premise
from vex_checks.ports.driven.source_rule_reader import SourceRuleReader
from vex_checks.ports.driven.vex_reader import VexReader
from vex_checks.ports.driving.claim_coverage_checker import (
    ClaimCoverageChecker,
    ClaimCoverageProblem,
    ClaimCoverageReport,
)


class CheckClaimCoverage(ClaimCoverageChecker):
    """Over the registry's image premises: its source premises are the source rules' to back."""

    def __init__(
        self,
        *,
        premises: Mapping[str, Premise],
        vex_paths: Sequence[PurePath],
        vex_reader: VexReader,
        source_rule_reader: SourceRuleReader,
    ) -> None:
        self._premises = premises
        self._vex_paths = vex_paths
        self._vex_reader = vex_reader
        self._source_rule_reader = source_rule_reader

    def check_claim_coverage(self) -> ClaimCoverageReport:
        claims = merge_claims(self._vex_reader.read_claims(path) for path in self._vex_paths)
        image_premise_ids = {
            advisory_id
            for advisory_id, premise in self._premises.items()
            if is_image_premise(premise)
        }
        source_rule_ids = self._source_rule_reader.read_source_rule_ids()
        backed_twice = image_premise_ids & source_rule_ids
        justification_by_backed_id = {
            **dict.fromkeys(image_premise_ids, JUSTIFICATION_BY_FAMILY["image"]),
            **dict.fromkeys(source_rule_ids, JUSTIFICATION_BY_FAMILY["source"]),
        }
        problems = [
            *(
                ClaimCoverageProblem(advisory_id, "has both an image premise and a source rule")
                for advisory_id in backed_twice
            ),
            *(
                ClaimCoverageProblem(advisory_id, "claim has no premise or source rule")
                for advisory_id in claims.keys() - justification_by_backed_id.keys()
            ),
            *(
                ClaimCoverageProblem(advisory_id, "premise has no claim")
                for advisory_id in image_premise_ids - claims.keys()
            ),
            *(
                ClaimCoverageProblem(advisory_id, "source rule has no claim")
                for advisory_id in source_rule_ids - claims.keys()
            ),
            *(
                ClaimCoverageProblem(
                    advisory_id,
                    f"justification {claims[advisory_id]!r}"
                    f" is not {justification_by_backed_id[advisory_id]!r}",
                )
                for advisory_id in claims.keys() & justification_by_backed_id.keys() - backed_twice
                if claims[advisory_id] != justification_by_backed_id[advisory_id]
            ),
        ]
        return ClaimCoverageReport(
            problems=tuple(sorted(problems, key=lambda problem: problem.advisory_id))
        )
