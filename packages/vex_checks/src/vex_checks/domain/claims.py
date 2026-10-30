"""The merge of several VEX documents' claims, each an ``advisory id -> justification`` mapping,
and their bijection with what backs them: the image premises, the source rules."""

from collections.abc import Iterable, Mapping, Set

from vex_checks.domain.claim_problem import ClaimProblem

IMAGE_PREMISE_JUSTIFICATION = "vulnerable_code_not_present"
SOURCE_RULE_JUSTIFICATION = "vulnerable_code_not_in_execute_path"


def merge_claims(claims_of_each_vex: Iterable[Mapping[str, str]]) -> dict[str, frozenset[str]]:
    """Each advisory's justifications across the documents: more than one is a conflict."""
    justifications_by_advisory_id: dict[str, set[str]] = {}
    for claims in claims_of_each_vex:
        for advisory_id, justification in claims.items():
            justifications_by_advisory_id.setdefault(advisory_id, set()).add(justification)
    return {
        advisory_id: frozenset(justifications)
        for advisory_id, justifications in justifications_by_advisory_id.items()
    }


def evaluate_claim_coverage(
    justifications_by_advisory_id: Mapping[str, frozenset[str]],
    *,
    image_premise_ids: Set[str],
    source_rule_ids: Set[str],
) -> list[ClaimProblem]:
    """The claims, image premises and source rules out of the bijection, each backing implying
    its justification; in the order of their advisory ids, then messages."""
    claimed_ids = justifications_by_advisory_id.keys()
    backed_twice = image_premise_ids & source_rule_ids
    justification_by_backed_id = {
        **dict.fromkeys(image_premise_ids, IMAGE_PREMISE_JUSTIFICATION),
        **dict.fromkeys(source_rule_ids, SOURCE_RULE_JUSTIFICATION),
    }
    problems = [
        *(
            ClaimProblem(advisory_id=advisory_id, message="justified differently across VEX files")
            for advisory_id, justifications in justifications_by_advisory_id.items()
            if len(justifications) > 1
        ),
        *(
            ClaimProblem(
                advisory_id=advisory_id, message="has both an image premise and a source rule"
            )
            for advisory_id in backed_twice
        ),
        *(
            ClaimProblem(advisory_id=advisory_id, message="claim has no premise or source rule")
            for advisory_id in claimed_ids - justification_by_backed_id.keys()
        ),
        *(
            ClaimProblem(advisory_id=advisory_id, message="premise has no claim")
            for advisory_id in image_premise_ids - claimed_ids
        ),
        *(
            ClaimProblem(advisory_id=advisory_id, message="source rule has no claim")
            for advisory_id in source_rule_ids - claimed_ids
        ),
        *(
            ClaimProblem(
                advisory_id=advisory_id,
                message=f"justification {justification!r}"
                f" is not {justification_by_backed_id[advisory_id]!r}",
            )
            for advisory_id in claimed_ids & justification_by_backed_id.keys() - backed_twice
            for justification in justifications_by_advisory_id[advisory_id]
            if justification != justification_by_backed_id[advisory_id]
        ),
    ]
    return sorted(problems, key=lambda problem: (problem.advisory_id, problem.message))
