"""The draws of a file's decisions, for the contracts that seed through ``DecisionWriter``."""

from datetime import datetime
from random import Random

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.file_target_decision import DatedDecision, FileTargetDecision
from p2pwatch.domain.identifiers import NodeId
from tests.support.draws import draw_instant, draw_text


def draw_target_id(randomness: Random) -> TargetId:
    """A target id, a text as ``draw_text`` draws it."""
    return TargetId(draw_text(randomness))


def draw_target_ids(randomness: Random, *, count: int) -> tuple[TargetId, ...]:
    """``count`` target ids, ascending."""
    return tuple(sorted(draw_target_id(randomness) for _ in range(count)))


def draw_decision_record(
    randomness: Random, *, tier: DecisionTier, target_id: TargetId | None = None
) -> DecisionRecord:
    """A record of ``tier`` by a drawn rule, for ``target_id`` drawn unless given."""
    return DecisionRecord(
        target_id=draw_target_id(randomness) if target_id is None else target_id,
        rule_name=draw_text(randomness),
        tier=tier,
    )


def draw_dated_decision(
    randomness: Random,
    *,
    file: FileKey,
    decision: FileTargetDecision,
    decided_at: datetime | None = None,
) -> DatedDecision[FileTargetDecision]:
    """``decision`` on ``file`` by a drawn node, ``decided_at`` drawn unless given."""
    return DatedDecision(
        file=file,
        decision=decision,
        decided_at=draw_instant(randomness) if decided_at is None else decided_at,
        node_id=NodeId(draw_text(randomness)),
    )
