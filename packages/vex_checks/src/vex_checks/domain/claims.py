"""The merge of several VEX documents' claims, each an ``advisory id -> justification`` mapping."""

from collections.abc import Iterable, Mapping


def merge_claims(claims_of_each_vex: Iterable[Mapping[str, str]]) -> dict[str, str]:
    """Refuses an advisory two documents justify differently."""
    merged: dict[str, str] = {}
    for claims in claims_of_each_vex:
        for advisory_id, justification in claims.items():
            existing = merged.get(advisory_id)
            if existing is not None and existing != justification:
                raise ValueError(f"{advisory_id} has conflicting justifications across VEX files")
            merged[advisory_id] = justification
    return merged
