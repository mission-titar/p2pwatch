from datetime import timedelta

import pytest

from tests.contracts.application.ports.driven.monotonic_clock_contract import (
    Action,
    ElapsedDuring,
    MonotonicClockContract,
)
from tests.fakes.adapters.driven.fake_monotonic_clock import FakeMonotonicClock


class TestFakeMonotonicClock(MonotonicClockContract):
    @pytest.fixture
    def monotonic_clock(self) -> FakeMonotonicClock:
        return FakeMonotonicClock()

    @pytest.fixture
    def elapsed_during(self, monotonic_clock: FakeMonotonicClock) -> ElapsedDuring:
        def elapsed(action: Action) -> timedelta:
            sleeps_before = len(monotonic_clock.sleeps)
            action()
            return sum(monotonic_clock.sleeps[sleeps_before:], timedelta())

        return elapsed
