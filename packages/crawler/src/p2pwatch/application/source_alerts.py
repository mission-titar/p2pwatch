"""Whether a source's useful reading is news to the community (source points spec, D5). Pure."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from p2pwatch.domain.source import SourceRole, SourceUsefulness
from p2pwatch.ports.source_repository import EarlierPoints


@dataclass(frozen=True)
class FirstUseful:
    """The source never had a useful point on this node."""


@dataclass(frozen=True)
class Reappeared:
    """The source had no useful or not-useful point on this node for ``absent_for``."""

    absent_for: timedelta


def source_alert(
    role: SourceRole,
    earlier_points: EarlierPoints,
    round_started_at: datetime,
    reappeared_after: timedelta,
) -> FirstUseful | Reappeared | None:
    """The alert a reading with ``role`` raises, from the source's points before the round."""
    if role.usefulness is not SourceUsefulness.USEFUL:
        return None
    if not earlier_points.has_useful_point:
        return FirstUseful()
    last = earlier_points.last_known_at
    if last is None or round_started_at - last <= reappeared_after:
        return None
    return Reappeared(round_started_at - last)
