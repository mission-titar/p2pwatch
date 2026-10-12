"""Whether a range a source opened is news to the community (stage 4 spec, D9). Pure."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from p2pwatch.domain.source import SourceGroup, SourceRole
from p2pwatch.ports.source_repository import EarlierRanges


@dataclass(frozen=True)
class FirstUseful:
    """The source never had a useful range on this node."""


@dataclass(frozen=True)
class UsefulAgain:
    """The source had no useful or not-useful range on this node for ``absent``."""

    absent: timedelta


def source_alert(
    role: SourceRole,
    earlier: EarlierRanges,
    round_started_at: datetime,
    reappeared_after: timedelta,
) -> FirstUseful | UsefulAgain | None:
    """The alert a range opened with ``role`` raises, from the source's ranges before the round."""
    if role.group is not SourceGroup.USEFUL:
        return None
    if not earlier.useful:
        return FirstUseful()
    last = earlier.last_known_at
    if last is None or round_started_at - last <= reappeared_after:
        return None
    return UsefulAgain(round_started_at - last)
