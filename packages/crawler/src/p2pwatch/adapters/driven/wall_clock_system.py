"""``SystemWallClock``: the system's time of day, in UTC."""

from datetime import UTC, datetime


class SystemWallClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
