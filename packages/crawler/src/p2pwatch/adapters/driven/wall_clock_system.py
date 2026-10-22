"""``SystemWallClock``: the system's time of day, in UTC."""

from datetime import UTC, datetime

from p2pwatch.application.ports.driven.wall_clock import WallClock


class SystemWallClock(WallClock):
    def now(self) -> datetime:
        return datetime.now(UTC)
