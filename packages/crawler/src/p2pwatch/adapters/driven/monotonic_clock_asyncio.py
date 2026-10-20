"""``AsyncioMonotonicClock``: the system's monotonic clock, and the event loop's sleep."""

import asyncio
import time
from datetime import timedelta

from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.ports.driven.clock import MonotonicClock


class AsyncioMonotonicClock(MonotonicClock):
    def now(self) -> MonotonicInstant:
        """Never asks for the running loop: the webui reads it from its own thread."""
        return MonotonicInstant(time.monotonic_ns())

    async def sleep(self, duration: timedelta) -> None:
        await asyncio.sleep(duration.total_seconds())
