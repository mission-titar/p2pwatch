"""An event loop whose clock is virtual: whenever every task waits, it jumps to the next timer
instead of sleeping, so concurrent tasks share one simulated time."""

import asyncio
import selectors
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from p2pwatch.domain.monotonic_instant import MonotonicInstant

# The instants the loop's time zero reads on each clock.
EPOCH = datetime(2026, 10, 9, tzinfo=UTC)
MONOTONIC_EPOCH = MonotonicInstant(nanoseconds=0)


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


class VirtualLoop(asyncio.SelectorEventLoop):
    def __init__(self) -> None:
        self._virtual = _VirtualSelector()
        super().__init__(self._virtual)

    def time(self) -> float:
        return self._virtual.time


@pytest.fixture
def virtual_loop() -> Iterator[VirtualLoop]:
    """A loop the test runs with ``run_until_complete``, handed out first to what reads its time."""
    loop = VirtualLoop()
    yield loop
    loop.close()
