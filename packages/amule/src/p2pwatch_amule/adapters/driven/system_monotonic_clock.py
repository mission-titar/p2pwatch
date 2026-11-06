import time
from datetime import timedelta

from p2pwatch_amule.application.ports.driven.monotonic_clock import MonotonicClock


class SystemMonotonicClock(MonotonicClock):
    """The system's monotonic clock, and a sleep that blocks the calling thread."""

    def sleep(self, duration: timedelta) -> None:
        time.sleep(duration.total_seconds())  # noqa: TID251
