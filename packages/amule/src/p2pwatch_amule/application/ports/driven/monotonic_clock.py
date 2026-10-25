from abc import ABC, abstractmethod
from datetime import timedelta

from p2pwatch_amule.domain.monotonic_instant import MonotonicInstant


class MonotonicClock(ABC):
    """Every interval and deadline kept in memory: a step of the wall clock never moves it."""

    @abstractmethod
    def now(self) -> MonotonicInstant:
        """The current monotonic instant, never before an earlier read."""

    @abstractmethod
    def sleep(self, duration: timedelta) -> None:
        """Returns once ``duration`` has passed on this clock, less at most a microsecond, as
        ``now()`` then reads."""
