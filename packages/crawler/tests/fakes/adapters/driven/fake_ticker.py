from dataclasses import dataclass
from datetime import timedelta

from p2pwatch.application.ports.driven.ticker import Operation, Tick, Ticker


@dataclass(kw_only=True)
class _OpenRun:
    tick: Tick
    period: timedelta
    elapsed: timedelta = timedelta(0)


class FakeTicker(Ticker):
    """Its time passes on demand: each ``tick()`` lets a period pass for the run open, if any;
    ``periods`` keeps each run's period."""

    def __init__(self) -> None:
        self.periods: list[timedelta] = []
        self._open_run: _OpenRun | None = None

    def run[T](self, operation: Operation[T], *, tick: Tick, period: timedelta) -> T:
        self.periods.append(period)
        self._open_run = _OpenRun(tick=tick, period=period)
        try:
            return operation()
        finally:
            self._open_run = None

    def tick(self) -> None:
        if self._open_run is not None:
            self._open_run.elapsed += self._open_run.period
            self._open_run.tick(elapsed=self._open_run.elapsed)
