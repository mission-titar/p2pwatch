"""Pure derivation of a target's coverage status (webui spec §5). No I/O.

The tier order comes from ``DecisionTier.rank``, the matching engine's own.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.identifiers import TargetId


class TargetCoverageStatus(StrEnum):
    """How far a target is recovered, its value the word the dashboard shows."""

    FOUND = "found"
    PARTIAL = "partial"
    NONE = "none"


@dataclass(frozen=True)
class TargetCoverage:
    target_id: TargetId
    status: TargetCoverageStatus
    best_tier: DecisionTier | None
    file_count: int


def coverage_of(target_id: TargetId, *, tiers: Sequence[DecisionTier]) -> TargetCoverage:
    """``tiers``: the tier of each file's latest decision for this target.

    Catalog-tier decisions are the ``keroro_large`` catch-all: any keroro file with no numeric
    token resolves to the smallest ``target_id`` (``001A``) via the engine tie-break, so counting
    them would make one episode look partially recovered while the catalog has identified nothing.
    """
    identified = [tier for tier in tiers if tier.identifies_target]
    if not identified:
        return TargetCoverage(
            target_id, status=TargetCoverageStatus.NONE, best_tier=None, file_count=0
        )
    best = max(identified, key=lambda tier: tier.rank)
    status = (
        TargetCoverageStatus.FOUND
        if best is DecisionTier.DOWNLOAD
        else TargetCoverageStatus.PARTIAL
    )
    return TargetCoverage(target_id, status=status, best_tier=best, file_count=len(identified))
