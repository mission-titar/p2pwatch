import time
from datetime import timedelta

from p2pwatch_amule.adapters.driven.system_monotonic_clock import SystemMonotonicClock


def test_now_reads_the_system_monotonic_clock() -> None:
    before = time.monotonic_ns()

    instant = SystemMonotonicClock().now()

    assert before <= instant.nanoseconds <= time.monotonic_ns()


def test_sleep_returns_once_its_duration_has_passed() -> None:
    before = time.monotonic_ns()

    SystemMonotonicClock().sleep(timedelta(milliseconds=20))

    assert time.monotonic_ns() - before >= 20_000_000
