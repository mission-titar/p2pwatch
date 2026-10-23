"""A file's latest decision for one target: the matcher's record, or its retraction (spec §7)."""

from dataclasses import dataclass

from catalog_matching.domain.engine import DecisionRecord


@dataclass(frozen=True)
class Retraction:
    """The file no longer matches ``target_id``: the append-only catalog appends this instead
    of deleting the record. The engine never produces it, so it is no tier."""

    target_id: str


type FileTargetDecision = DecisionRecord | Retraction
