"""Whether a source's useful reading is news to the community (source points spec, D5). Pure."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from p2pwatch.domain.source import SourceGroup, SourceRole
from p2pwatch.ports.source_repository import EarlierPoints


@dataclass(frozen=True)
class FirstUseful:
    """The source never had a useful point on this node."""


@dataclass(frozen=True)
class UsefulAgain:
    """The source had no useful or not-useful point on this node for ``absent``."""

    absent: timedelta


def source_alert(
    role: SourceRole,
    earlier: EarlierPoints,
    round_started_at: datetime,
    reappeared_after: timedelta,
) -> FirstUseful | UsefulAgain | None:
    """The alert a reading with ``role`` raises, from the source's points before the round."""
    if role.group is not SourceGroup.USEFUL:
        return None
    if not earlier.useful:
        return FirstUseful()
    last = earlier.last_known_at
    if last is None or round_started_at - last <= reappeared_after:
        return None
    return UsefulAgain(round_started_at - last)
