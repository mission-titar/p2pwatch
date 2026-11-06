import asyncio

import pytest

from tests.contracts.application.ports.driven.monotonic_clock_contract import (
    MonotonicClockContract,
)
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock


class TestFakeLoopMonotonicClock(MonotonicClockContract):
    @pytest.fixture
    def monotonic_clock(self, running_loop: asyncio.AbstractEventLoop) -> FakeLoopMonotonicClock:
        return FakeLoopMonotonicClock(running_loop)
