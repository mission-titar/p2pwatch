import asyncio
from datetime import timedelta

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from tests.support.virtual_time import MONOTONIC_EPOCH


class FakeLoopMonotonicClock(MonotonicClock):
    """The time of the loop it is given as the ``MonotonicClock`` port; ``sleep`` must run on it."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def now(self) -> MonotonicInstant:
        return MONOTONIC_EPOCH + timedelta(seconds=self._loop.time())

    async def sleep(self, duration: timedelta) -> None:
        await asyncio.sleep(duration.total_seconds())
