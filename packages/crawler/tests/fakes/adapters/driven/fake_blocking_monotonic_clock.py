import asyncio
from datetime import timedelta
from typing import NoReturn

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock


class FakeBlockingMonotonicClock(MonotonicClock):
    """Monotonic clock whose ``sleep`` BLOCKS for good (the wake must win and cancel the sleep).

    ``sleep`` never resolves, so the pending sleep_task is cancelled.
    """

    def now(self) -> NoReturn:
        raise AssertionError("the download loop reads no time from its sleep's clock")

    async def sleep(self, duration: timedelta) -> None:
        await asyncio.Event().wait()  # NEVER resolves
