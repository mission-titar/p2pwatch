from datetime import timedelta
from typing import Protocol

from p2pwatch_amule.application.ports.driven.monotonic_clock import MonotonicClock


class SleepCallback(Protocol):
    def __call__(self) -> None: ...


class FakeMonotonicClock(MonotonicClock):
    """Its ``sleep`` records the duration as passed, returns at once, then calls ``on_sleep``."""

    def __init__(self) -> None:
        self.sleeps: list[timedelta] = []
        self.on_sleep: SleepCallback = lambda: None

    def sleep(self, duration: timedelta) -> None:
        self.sleeps.append(duration)
        self.on_sleep()
