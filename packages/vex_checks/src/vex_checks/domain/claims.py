"""The merge of several VEX documents' claims, each an ``advisory id -> justification`` mapping,
and the justification each backing implies."""

from collections.abc import Iterable, Mapping

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
