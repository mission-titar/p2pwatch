import asyncio

import pytest_asyncio

from tests.contracts.application.ports.driven.monotonic_clock_contract import (
    MonotonicClockContract,
)
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock


class TestFakeLoopMonotonicClock(MonotonicClockContract):
    @pytest_asyncio.fixture
    async def monotonic_clock(self) -> FakeLoopMonotonicClock:
        return FakeLoopMonotonicClock(asyncio.get_running_loop())
