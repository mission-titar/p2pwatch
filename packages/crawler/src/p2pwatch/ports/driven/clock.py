"""Time, injectable: ``WallClock`` stamps, ``MonotonicClock`` measures every interval and deadline
kept in memory."""

from datetime import datetime, timedelta
from typing import Protocol

from p2pwatch.domain.monotonic_instant import MonotonicInstant


class WallClock(Protocol):
    """The UTC time of day, aware: every stamp a row, an event or a display carries."""

    def now(self) -> datetime: ...


class MonotonicClock(Protocol):
    """Every interval and deadline kept in memory: a step of the wall clock never moves it."""

    def now(self) -> MonotonicInstant: ...

    async def sleep(self, duration: timedelta) -> None: ...
