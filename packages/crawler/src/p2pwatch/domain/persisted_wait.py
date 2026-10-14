"""A wait that survives a restart: its start on the wall clock and its duration."""

from datetime import datetime, timedelta


def remaining_wait(started_at: datetime, duration: timedelta, now: datetime) -> timedelta:
    """What is left of the wait, its elapsed time clamped to [0, ``duration``]: a clock stepped
    back never lengthens a wait past its own duration."""
    elapsed = min(max(now - started_at, timedelta(0)), duration)
    return duration - elapsed
