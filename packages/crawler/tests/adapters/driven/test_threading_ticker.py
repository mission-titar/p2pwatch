import threading
from datetime import timedelta

import pytest

from p2pwatch.adapters.driven.asyncio_monotonic_clock import AsyncioMonotonicClock
from p2pwatch.adapters.driven.threading_ticker import ThreadingTicker
from p2pwatch.application.ports.driven.ticker import Ticker
from tests.contracts.application.ports.driven.ticker_contract import TickerContract


class TestThreadingTicker(TickerContract):
    @pytest.fixture
    def ticker(self) -> ThreadingTicker:
        return ThreadingTicker(AsyncioMonotonicClock())

    def let_periods_pass(self, ticker: Ticker, *, periods: int) -> None:
        """Its time passes alone."""


def test_a_tick_runs_on_another_thread_than_the_operation() -> None:
    threads: list[int] = []
    ticked = threading.Event()

    def tick(*, elapsed: timedelta) -> None:
        threads.append(threading.get_ident())
        ticked.set()

    ThreadingTicker(AsyncioMonotonicClock()).run(
        lambda: ticked.wait(5.0), tick=tick, period=timedelta(milliseconds=10)
    )

    assert threads
    assert threading.get_ident() not in threads
