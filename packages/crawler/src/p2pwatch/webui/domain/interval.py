"""The interval a page reads its periods and its timeline in (source points spec, D6)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# The longest interval a page reads, which bounds a display's cost.
MAX_SPAN = timedelta(days=7)
PRESETS: tuple[tuple[str, timedelta], ...] = (
    ("Last hour", timedelta(hours=1)),
    ("Last 6 hours", timedelta(hours=6)),
    ("Last 24 hours", timedelta(hours=24)),
    ("Last 7 days", MAX_SPAN),
)
# An earlier instant is read as absent, so that no step back overflows ``datetime``.
_EARLIEST = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Interval:
    """From ``since`` included to ``until`` excluded, in UTC; ``cut`` when the request was longer
    than ``MAX_SPAN``."""

    since: datetime
    until: datetime
    cut: bool = False

    def shifted(self, steps: int) -> "Interval":
        """The interval moved by ``steps`` times its own length: Previous is -1, Next is 1."""
        span = self.until - self.since
        return Interval(self.since + steps * span, self.until + steps * span)


def parse_instant(raw: str | None) -> datetime | None:
    """An ISO 8601 instant to the second, read as UTC without an offset; ``None`` when absent,
    malformed or before the epoch."""
    try:
        parsed = datetime.fromisoformat((raw or "").strip())
        instant = parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)
    except (ValueError, OverflowError):
        return None
    return instant.replace(microsecond=0) if instant >= _EARLIEST else None


def requested_interval(raw_from: str | None, raw_to: str | None, now: datetime) -> Interval:
    """The query's interval: ``to`` is ``now`` when absent, ``from`` is ``MAX_SPAN`` before ``to``
    when absent or not before it, and a longer one keeps the ``MAX_SPAN`` ending at ``to``."""
    until = parse_instant(raw_to) or now
    since = parse_instant(raw_from)
    if since is None or since >= until:
        return last(MAX_SPAN, until)
    if until - since > MAX_SPAN:
        return Interval(until - MAX_SPAN, until, cut=True)
    return Interval(since, until)


def last(span: timedelta, now: datetime) -> Interval:
    """The ``span`` ending ``now``, a preset's interval."""
    return Interval(now - span, now)
