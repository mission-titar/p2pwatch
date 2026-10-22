import asyncio
from datetime import timedelta

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from tests.support.virtual_time import MONOTONIC_EPOCH


class FakeLoopMonotonicClock(MonotonicClock):
    """The running loop's time as the ``MonotonicClock`` port."""

    def now(self) -> MonotonicInstant:
        return MONOTONIC_EPOCH + timedelta(seconds=asyncio.get_running_loop().time())

    async def sleep(self, duration: timedelta) -> None:
        await asyncio.sleep(duration.total_seconds())
