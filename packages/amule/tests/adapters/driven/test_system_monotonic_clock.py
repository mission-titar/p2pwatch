import time
from datetime import timedelta

import pytest

from p2pwatch_amule.adapters.driven.system_monotonic_clock import SystemMonotonicClock
from tests.contracts.application.ports.driven.monotonic_clock_contract import (
    Action,
    ElapsedDuring,
    MonotonicClockContract,
)


class TestSystemMonotonicClock(MonotonicClockContract):
    @pytest.fixture
    def monotonic_clock(self) -> SystemMonotonicClock:
        return SystemMonotonicClock()

    @pytest.fixture
    def elapsed_during(self) -> ElapsedDuring:
        def elapsed(action: Action) -> timedelta:
            before = time.monotonic_ns()  # noqa: TID251
            action()
            return timedelta(microseconds=(time.monotonic_ns() - before) / 1000)  # noqa: TID251

        return elapsed
