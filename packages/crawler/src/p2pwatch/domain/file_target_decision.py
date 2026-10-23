"""A file's latest decision for one target: the matcher's record, or its retraction (spec §7)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from catalog_matching.domain.engine import DecisionRecord


@dataclass(frozen=True)
class Retraction:
    """The file no longer matches ``target_id``: the append-only catalog appends this instead
    of deleting the record. The engine never produces it, so it is no tier."""

    target_id: str


type FileTargetDecision = DecisionRecord | Retraction


def records_to_write(
    fresh: Sequence[DecisionRecord], persisted: Mapping[str, FileTargetDecision]
) -> tuple[FileTargetDecision, ...]:
    """What the file's fresh records change in its persisted decisions, by target: each fresh
    record unlike its persisted one, then a retraction per target the fresh ones dropped."""
    fresh_target_ids = {record.target_id for record in fresh}
    return (
        *(record for record in fresh if persisted.get(record.target_id) != record),
        *(
            Retraction(target_id)
            for target_id in sorted(persisted)
            if target_id not in fresh_target_ids
            and not isinstance(persisted[target_id], Retraction)
        ),
    )
