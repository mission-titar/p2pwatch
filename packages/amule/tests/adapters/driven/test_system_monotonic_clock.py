import time

import pytest

from p2pwatch_amule.adapters.driven.system_monotonic_clock import SystemMonotonicClock
from tests.contracts.application.ports.driven.monotonic_clock_contract import (
    MonotonicClockContract,
)


class TestSystemMonotonicClock(MonotonicClockContract):
    @pytest.fixture
    def monotonic_clock(self) -> SystemMonotonicClock:
        return SystemMonotonicClock()


def test_now_reads_the_system_monotonic_clock() -> None:
    before = time.monotonic_ns()

    instant = SystemMonotonicClock().now()

    assert before <= instant.nanoseconds <= time.monotonic_ns()
