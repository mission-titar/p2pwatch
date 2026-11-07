"""``ThreadingTicker``: ticks from a thread of its own, which SQLite lets run since it releases
the GIL while it works."""

import threading
from datetime import timedelta

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.ticker import Operation, Tick, Ticker


class ThreadingTicker(Ticker):
    def __init__(self, monotonic_clock: MonotonicClock) -> None:
        self._monotonic_clock = monotonic_clock

    def run[T](self, operation: Operation[T], *, tick: Tick, period: timedelta) -> T:
        ended = threading.Event()
        began = self._monotonic_clock.now()

        def tick_until_ended() -> None:
            # Not MonotonicClock.sleep: it waits on the event loop the operation holds.
            while not ended.wait(period.total_seconds()):
                tick(elapsed=self._monotonic_clock.now() - began)

        ticking = threading.Thread(target=tick_until_ended, name="ticker", daemon=True)
        ticking.start()
        try:
            return operation()
        finally:
            ended.set()
            ticking.join()
