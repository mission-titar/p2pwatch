import time
from datetime import timedelta

from p2pwatch_amule.domain.monotonic_instant import MonotonicInstant
from p2pwatch_amule.ports.driven.monotonic_clock import MonotonicClock


class SystemMonotonicClock(MonotonicClock):
    """The system's monotonic clock, and a sleep that blocks the calling thread."""

    def now(self) -> MonotonicInstant:
        return MonotonicInstant(time.monotonic_ns())

    def sleep(self, duration: timedelta) -> None:
        time.sleep(duration.total_seconds())
