import asyncio
import time
from datetime import timedelta

from p2pwatch.adapters.driven.monotonic_clock_asyncio import AsyncioMonotonicClock
from p2pwatch.ports.driven.clock import MonotonicInstant
from p2pwatch_testing.virtual_time import run_virtual


def test_now_reads_the_monotonic_clock_outside_any_event_loop() -> None:
    before = MonotonicInstant(time.monotonic_ns())

    instant = AsyncioMonotonicClock().now()

    assert before <= instant <= MonotonicInstant(time.monotonic_ns())


def test_sleep_waits_its_duration_on_the_event_loop() -> None:
    async def slept_until() -> float:
        await AsyncioMonotonicClock().sleep(timedelta(milliseconds=1500))
        return asyncio.get_running_loop().time()

    assert run_virtual(slept_until()) == 1.5
