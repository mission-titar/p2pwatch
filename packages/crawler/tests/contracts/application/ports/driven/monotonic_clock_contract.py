"""The promise of the ``MonotonicClock`` port. A real clock sleeps for real: 10 ms per sleep."""

import asyncio
from abc import ABC, abstractmethod
from datetime import timedelta

import pytest

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock

_SLEEP = timedelta(milliseconds=10)


class MonotonicClockContract(ABC):
    pytestmark = pytest.mark.asyncio

    @pytest.fixture
    @abstractmethod
    def monotonic_clock(self) -> MonotonicClock:
        """A clock whose ``sleep`` waits on the test's running loop."""

    async def test_now_never_decreases(self, monotonic_clock: MonotonicClock) -> None:
        readings = [monotonic_clock.now() for _ in range(3)]

        assert readings == sorted(readings)

    async def test_now_after_a_sleep_is_its_duration_later_less_a_microsecond(
        self, monotonic_clock: MonotonicClock
    ) -> None:
        before = monotonic_clock.now()

        await monotonic_clock.sleep(_SLEEP)

        assert monotonic_clock.now() - before >= _SLEEP - timedelta(microseconds=1)

    async def test_now_is_read_from_a_thread_with_no_running_loop(
        self, monotonic_clock: MonotonicClock
    ) -> None:
        before = monotonic_clock.now()

        from_thread = await asyncio.to_thread(monotonic_clock.now)

        assert before <= from_thread <= monotonic_clock.now()
