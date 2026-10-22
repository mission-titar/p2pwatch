from collections.abc import Callable
from datetime import timedelta

from p2pwatch_amule.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch_amule.domain.monotonic_instant import MonotonicInstant


class FakeMonotonicClock(MonotonicClock):
    """Its ``sleep`` records the duration and advances ``now`` at once, then calls ``on_sleep``."""

    def __init__(self) -> None:
        self.instant = MonotonicInstant(0)
        self.sleeps: list[timedelta] = []
        self.on_sleep: Callable[[], None] = lambda: None

    def now(self) -> MonotonicInstant:
        return self.instant

    def sleep(self, duration: timedelta) -> None:
        self.sleeps.append(duration)
        microseconds = duration // timedelta(microseconds=1)
        self.instant = MonotonicInstant(self.instant.nanoseconds + microseconds * 1000)
        self.on_sleep()
