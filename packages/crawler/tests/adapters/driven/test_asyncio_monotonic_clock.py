import pytest

from p2pwatch.adapters.driven.asyncio_monotonic_clock import AsyncioMonotonicClock
from tests.contracts.application.ports.driven.monotonic_clock_contract import (
    MonotonicClockContract,
)


class TestAsyncioMonotonicClock(MonotonicClockContract):
    @pytest.fixture
    def monotonic_clock(self) -> AsyncioMonotonicClock:
        return AsyncioMonotonicClock()
