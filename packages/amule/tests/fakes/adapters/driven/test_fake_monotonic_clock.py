import pytest

from tests.contracts.application.ports.driven.monotonic_clock_contract import (
    MonotonicClockContract,
)
from tests.fakes.adapters.driven.fake_monotonic_clock import FakeMonotonicClock


class TestFakeMonotonicClock(MonotonicClockContract):
    @pytest.fixture
    def monotonic_clock(self) -> FakeMonotonicClock:
        return FakeMonotonicClock()
