from abc import ABC, abstractmethod
from datetime import timedelta


class MonotonicClock(ABC):
    """Every interval and deadline kept in memory: a step of the wall clock never moves it."""

    @abstractmethod
    def sleep(self, duration: timedelta) -> None:
        """Returns once ``duration`` has passed on this clock, less at most a microsecond."""
