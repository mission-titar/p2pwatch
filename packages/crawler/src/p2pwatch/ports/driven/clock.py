"""Time, injectable: ``WallClock`` stamps, ``MonotonicClock`` measures every interval and deadline
kept in memory."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from p2pwatch.domain.monotonic_instant import MonotonicInstant


class WallClock(ABC):
    """The UTC time of day, aware: every stamp a row, an event or a display carries."""

    @abstractmethod
    def now(self) -> datetime:
        """The current UTC time, aware."""


class MonotonicClock(ABC):
    """Every interval and deadline kept in memory: a step of the wall clock never moves it."""

    @abstractmethod
    def now(self) -> MonotonicInstant:
        """The current monotonic instant."""

    @abstractmethod
    async def sleep(self, duration: timedelta) -> None:
        """Returns once ``duration`` has passed on this clock."""
