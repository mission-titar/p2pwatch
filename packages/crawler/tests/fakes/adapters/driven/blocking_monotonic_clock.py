import asyncio
from datetime import timedelta

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.domain.monotonic_instant import MonotonicInstant


class FakeBlockingMonotonicClock(MonotonicClock):
    """Monotonic clock whose ``sleep`` BLOCKS for good (the wake must win and cancel the sleep).

    ``now`` is unused by the loop; ``sleep`` never resolves, so the pending sleep_task is cancelled.
    """

    def now(self) -> MonotonicInstant:
        return MonotonicInstant(0)

    async def sleep(self, duration: timedelta) -> None:
        await asyncio.Event().wait()  # NEVER resolves
