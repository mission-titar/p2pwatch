"""The promise of the ``MonotonicClock`` port. A real clock sleeps for real: 10 ms per sleep."""

from abc import ABC, abstractmethod
from datetime import timedelta

import pytest

from p2pwatch_amule.application.ports.driven.monotonic_clock import MonotonicClock

_SLEEP = timedelta(milliseconds=10)


class MonotonicClockContract(ABC):
    @pytest.fixture
    @abstractmethod
    def monotonic_clock(self) -> MonotonicClock:
        """The clock under test."""

    def test_now_never_decreases(self, monotonic_clock: MonotonicClock) -> None:
        readings = [monotonic_clock.now().nanoseconds for _ in range(3)]

        assert readings == sorted(readings)

    def test_now_after_a_sleep_is_its_duration_later_less_a_microsecond(
        self, monotonic_clock: MonotonicClock
    ) -> None:
        before = monotonic_clock.now()

        monotonic_clock.sleep(_SLEEP)

        assert monotonic_clock.now() - before >= _SLEEP - timedelta(microseconds=1)
