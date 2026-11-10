from datetime import timedelta
from typing import Protocol

from p2pwatch.application.ports.driven.ticker import Operation, Tick, Ticker


class ShutdownRequest(Protocol):
    def __call__(self) -> None: ...


class FakeShutdownRequestingTicker(Ticker):
    """Calls ``request_shutdown`` as each run starts, then runs it, never ticking."""

    def __init__(self, request_shutdown: ShutdownRequest) -> None:
        self._request_shutdown = request_shutdown

    def run[T](self, operation: Operation[T], *, tick: Tick, period: timedelta) -> T:
        self._request_shutdown()
        return operation()
