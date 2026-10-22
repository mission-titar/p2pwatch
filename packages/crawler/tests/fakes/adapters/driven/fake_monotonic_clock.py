import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.domain.monotonic_instant import MonotonicInstant

if TYPE_CHECKING:  # a cycle: FakeTime builds its clocks
    from tests.fakes.adapters.driven.fake_time import FakeTime


class FakeMonotonicClock(MonotonicClock):
    """Its ``sleep`` advances the timeline at once, without a real wait."""

    def __init__(self, fake_time: "FakeTime") -> None:
        self._fake_time = fake_time

    def now(self) -> MonotonicInstant:
        return self._fake_time._monotonic_now

    async def sleep(self, duration: timedelta) -> None:
        self._fake_time.sleeps.append(duration)
        self._fake_time.advance(duration)
        await asyncio.sleep(0)  # yield control without a real wait
