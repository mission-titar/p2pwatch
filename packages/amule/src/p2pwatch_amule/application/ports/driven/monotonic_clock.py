from abc import ABC, abstractmethod
from datetime import timedelta


class MonotonicClock(ABC):
    """The poll's sleep, on a clock a step of the wall clock never moves."""

    @abstractmethod
    def sleep(self, duration: timedelta) -> None:
        """Returns once ``duration`` has passed on this clock, less at most a microsecond."""
