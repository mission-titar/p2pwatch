"""The stores' timestamp format, ``utc_iso``, alone here since ``SqliteDatabaseOpener`` opens and
migrates the databases; the backlog's "Every stamp an integer of microseconds since the epoch"
removes it with this module.

ISO-8601 UTC as TEXT (spec §3), FIXED microseconds so that lexicographic order IS chronological
order (the FIFO claim sorts on ``enqueued_at``).
"""

from datetime import UTC, datetime


def utc_iso(moment: datetime) -> str:
    """Fixed-width ISO-8601 UTC (microseconds ALWAYS written), e.g.
    ``2026-06-11T12:00:00.000000+00:00``. ``moment`` must be AWARE (ENFORCED: naive →
    ``ValueError``); a non-UTC zone is normalized, never stored as-is."""
    if moment.tzinfo is None:
        raise ValueError("utc_iso requires an aware datetime")
    return moment.astimezone(UTC).isoformat(timespec="microseconds")
