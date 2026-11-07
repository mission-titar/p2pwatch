"""The promise of the ``Ticker`` port. A real ticker waits for real: 10 ms per period."""

import threading
from abc import ABC, abstractmethod
from datetime import timedelta

import pytest

from p2pwatch.application.ports.driven.ticker import Ticker

_PERIOD = timedelta(milliseconds=10)
_TIMEOUT = timedelta(seconds=5)


class _Ticks:
    """Keeps each tick's elapsed time, and lets a test wait for the ``count``-th."""

    def __init__(self) -> None:
        self.elapsed: list[timedelta] = []
        self._changed = threading.Condition()

    def __call__(self, *, elapsed: timedelta) -> None:
        with self._changed:
            self.elapsed.append(elapsed)
            self._changed.notify_all()

    def wait_for(self, count: int, *, timeout: timedelta = _TIMEOUT) -> bool:
        with self._changed:
            return self._changed.wait_for(
                lambda: len(self.elapsed) >= count, timeout.total_seconds()
            )


class TickerContract(ABC):
    @pytest.fixture
    @abstractmethod
    def ticker(self) -> Ticker:
        """A ticker no run has used yet."""

    @abstractmethod
    def let_periods_pass(self, ticker: Ticker, *, periods: int) -> None:
        """Lets ``periods`` periods pass for ``ticker``, from inside its operation or after it,
        for a ticker whose time does not pass alone."""

    def test_run_returns_what_its_operation_returns(self, ticker: Ticker) -> None:
        assert ticker.run(lambda: 42, tick=_Ticks(), period=_PERIOD) == 42

    def test_run_raises_what_its_operation_raises(self, ticker: Ticker) -> None:
        def operation() -> None:
            raise ValueError("the operation failed")

        with pytest.raises(ValueError, match="the operation failed"):
            ticker.run(operation, tick=_Ticks(), period=_PERIOD)

    def test_each_tick_comes_a_period_after_the_previous_while_the_operation_runs(
        self, ticker: Ticker
    ) -> None:
        ticks = _Ticks()

        def operation() -> bool:
            self.let_periods_pass(ticker, periods=3)
            return ticks.wait_for(3)

        assert ticker.run(operation, tick=ticks, period=_PERIOD)
        starts = [timedelta(0), *ticks.elapsed[:-1]]
        less_a_microsecond = _PERIOD - timedelta(microseconds=1)
        assert all(
            elapsed - start >= less_a_microsecond
            for start, elapsed in zip(starts, ticks.elapsed, strict=True)
        )

    def test_no_tick_comes_once_run_has_returned(self, ticker: Ticker) -> None:
        ticks = _Ticks()

        def operation() -> bool:
            self.let_periods_pass(ticker, periods=1)
            return ticks.wait_for(1)

        assert ticker.run(operation, tick=ticks, period=_PERIOD)
        count = len(ticks.elapsed)
        self.let_periods_pass(ticker, periods=1)
        assert not ticks.wait_for(count + 1, timeout=10 * _PERIOD)

    def test_run_returns_without_waiting_for_its_period(self, ticker: Ticker) -> None:
        returned = threading.Event()

        def run_an_hour_long_period() -> None:
            ticker.run(lambda: None, tick=_Ticks(), period=timedelta(hours=1))
            returned.set()

        threading.Thread(target=run_an_hour_long_period, daemon=True).start()

        assert returned.wait(_TIMEOUT.total_seconds())
