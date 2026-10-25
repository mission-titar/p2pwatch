import pytest

from tests.contracts.application.ports.driven.monotonic_clock_contract import (
    MonotonicClockContract,
)
from tests.fakes.adapters.driven.fake_ticking_monotonic_clock import FakeTickingMonotonicClock
from tests.fakes.adapters.driven.fake_time import FakeTime


class TestFakeTickingMonotonicClock(MonotonicClockContract):
    @pytest.fixture
    def monotonic_clock(self) -> FakeTickingMonotonicClock:
        return FakeTickingMonotonicClock(FakeTime())
