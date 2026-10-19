"""The interval a page reads its periods and its observations in (source points spec, D6)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

# The longest interval a page reads, which bounds a display's cost.
MAX_INTERVAL_SPAN = timedelta(days=7)


@dataclass(frozen=True)
class Interval:
    """From ``since`` included to ``until`` excluded, in UTC; ``clamped`` when the request was
    longer than ``MAX_INTERVAL_SPAN``."""

    since: datetime
    until: datetime
    clamped: bool = False

    def shifted(self, steps: int) -> "Interval":
        """The interval moved by ``steps`` times its own length: Previous is -1, Next is 1."""
        span = self.until - self.since
        return Interval(self.since + steps * span, self.until + steps * span)


def requested_interval(
    requested_since: datetime | None, requested_until: datetime | None, now: datetime
) -> Interval:
    """The interval asked for: ``until`` is ``now`` when absent, ``since`` is
    ``MAX_INTERVAL_SPAN`` before ``until`` when absent or not before it, and a longer one keeps
    the ``MAX_INTERVAL_SPAN`` ending at ``until``."""
    until = requested_until or now
    since = requested_since
    if since is None or since >= until:
        return interval_ending(until, MAX_INTERVAL_SPAN)
    if until - since > MAX_INTERVAL_SPAN:
        return Interval(until - MAX_INTERVAL_SPAN, until, clamped=True)
    return Interval(since, until)


def interval_ending(now: datetime, span: timedelta) -> Interval:
    """The ``span`` ending ``now``, a preset's interval."""
    return Interval(now - span, now)
