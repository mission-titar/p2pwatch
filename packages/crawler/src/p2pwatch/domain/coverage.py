"""Pure derivation of a target's coverage status (webui spec §5). No I/O.

The tier order comes from ``catalog_matching.domain.config.TIER_RANK`` (source of truth shared
with the matching engine). Without this sharing, the webui reinvented its own divergent
table: a 4th tier or a rename would have silently skewed the coverage.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from catalog_matching.domain.config import TIER_RANK


@dataclass(frozen=True)
class TargetCoverage:
    target_id: str
    status: str  # "found" | "partial" | "none"
    best_tier: str | None  # "download" | "notify" | "catalog" | None
    file_count: int


def coverage_of(target_id: str, tiers: Sequence[str]) -> TargetCoverage:
    """``tiers``: the tier of each file's latest decision for this target.

    Catalog-tier decisions are the ``keroro_large`` catch-all: any keroro file with no numeric
    token resolves to the smallest ``target_id`` (``001A``) via the engine tie-break, so counting
    them would make one episode look partially recovered while the catalog has identified nothing.
    They do NOT count as coverage of an episode (same ``tier == "catalog"`` criterion the ``/files``
    "unidentified" mask uses in ``adapters.driving.webui.app._resolve_target_display``).
    """
    identified = [tier for tier in tiers if tier != "catalog"]
    if not identified:
        return TargetCoverage(target_id, status="none", best_tier=None, file_count=0)
    # TIER_RANK: increasing integer = stronger tier (download > notify); an unknown tier falls
    # back to ``-1`` (below the weakest), neutral with respect to the choice.
    best = max(identified, key=lambda tier: TIER_RANK.get(tier, -1))
    status = "found" if best == "download" else "partial"
    return TargetCoverage(target_id, status=status, best_tier=best, file_count=len(identified))
