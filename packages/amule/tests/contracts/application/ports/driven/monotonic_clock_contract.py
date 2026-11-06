"""The promise of the ``MonotonicClock`` port. A real clock sleeps for real: 10 ms per sleep."""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Protocol

import pytest

from p2pwatch_amule.application.ports.driven.monotonic_clock import MonotonicClock

_SLEEP = timedelta(milliseconds=10)


class Action(Protocol):
    def __call__(self) -> None: ...


class ElapsedDuring(Protocol):
    def __call__(self, action: Action) -> timedelta: ...


class MonotonicClockContract(ABC):
    @pytest.fixture
    @abstractmethod
    def monotonic_clock(self) -> MonotonicClock:
        """The clock under test."""

    @pytest.fixture
    @abstractmethod
    def elapsed_during(self, monotonic_clock: MonotonicClock) -> ElapsedDuring:
        """How long ``action`` takes on the time ``monotonic_clock`` follows."""

    def test_a_sleep_returns_once_its_duration_has_passed_less_a_microsecond(
        self, *, monotonic_clock: MonotonicClock, elapsed_during: ElapsedDuring
    ) -> None:
        elapsed = elapsed_during(lambda: monotonic_clock.sleep(_SLEEP))

        assert elapsed >= _SLEEP - timedelta(microseconds=1)
