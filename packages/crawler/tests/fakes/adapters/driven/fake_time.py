from datetime import UTC, datetime, timedelta

from p2pwatch.domain.monotonic_instant import MonotonicInstant
from tests.fakes.adapters.driven.fake_monotonic_clock import FakeMonotonicClock
from tests.fakes.adapters.driven.fake_wall_clock import FakeWallClock


class FakeTime:
    """One fake timeline the test drives, read through ``wall`` and ``monotonic``: ``advance``
    moves both clocks, ``step_wall`` the wall clock alone, as a clock step does."""

    def __init__(self, start: datetime | None = None) -> None:
        self._wall_now = start or datetime(2026, 6, 12, tzinfo=UTC)
        self._monotonic_now = MonotonicInstant(0)
        self.sleeps: list[timedelta] = []
        self.wall = FakeWallClock(self)
        self.monotonic = FakeMonotonicClock(self)

    def advance(self, duration: timedelta) -> None:
        self._wall_now += duration
        self._monotonic_now += duration

    def step_wall(self, step: timedelta) -> None:
        self._wall_now += step
