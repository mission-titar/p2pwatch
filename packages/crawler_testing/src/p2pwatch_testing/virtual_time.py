"""An event loop whose clock is virtual: whenever every task waits, it jumps to the next timer
instead of sleeping, so concurrent tasks share one simulated time."""

import asyncio
import selectors
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from p2pwatch.ports.driven.clock import MonotonicInstant

# The instants the loop's time zero reads on each clock.
EPOCH = datetime(2026, 10, 9, tzinfo=UTC)
MONOTONIC_EPOCH = MonotonicInstant(0)


class _VirtualSelector(selectors.DefaultSelector):
    """Never blocks: the wait the loop asks for advances the virtual time instead."""

    def __init__(self) -> None:
        super().__init__()
        self.time = 0.0

    def select(self, timeout: float | None = None) -> list[tuple[selectors.SelectorKey, int]]:
        assert not super().select(0), "I/O is ready, which a virtual wait would skip past"
        assert timeout is not None, "every task waits and no timer is set: a deadlock"
        self.time += timeout
        return []


class _VirtualLoop(asyncio.SelectorEventLoop):
    def __init__(self) -> None:
        self._virtual = _VirtualSelector()
        super().__init__(self._virtual)

    def time(self) -> float:
        return self._virtual.time


class LoopWallClock:
    """The running loop's time as the ``WallClock`` port."""

    def now(self) -> datetime:
        return EPOCH + timedelta(seconds=asyncio.get_running_loop().time())


class LoopMonotonicClock:
    """The running loop's time as the ``MonotonicClock`` port."""

    def now(self) -> MonotonicInstant:
        return MONOTONIC_EPOCH + timedelta(seconds=asyncio.get_running_loop().time())

    async def sleep(self, duration: timedelta) -> None:
        await asyncio.sleep(duration.total_seconds())


def run_virtual[T](main: Coroutine[Any, Any, T]) -> T:
    loop = _VirtualLoop()
    try:
        return loop.run_until_complete(main)
    finally:
        loop.close()
