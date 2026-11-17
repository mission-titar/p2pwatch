"""``WebuiThreadWatch``: looks every minute whether the webui's thread still runs."""

from datetime import timedelta
from typing import Protocol

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.steps.work import Work

_WATCH_PERIOD = timedelta(minutes=1)


# Whether the webui's thread still runs, such as ``UvicornServerThread.is_alive``.
class WebuiThreadAlive(Protocol):
    def __call__(self) -> bool: ...


class WebuiThreadEndedError(Exception):
    """The webui's thread has ended while the node runs: a bug, since it serves until the
    shutdown."""


class WebuiThreadWatch(Work):
    """Looks every minute whether the webui's thread still runs, its first look a minute after the
    start; a thread that has ended is a bug of the webui."""

    def __init__(self, *, thread_alive: WebuiThreadAlive, monotonic_clock: MonotonicClock) -> None:
        self._thread_alive = thread_alive
        self._monotonic_clock = monotonic_clock

    def __str__(self) -> str:
        return "webui thread watch"

    async def wait_for_next_turn(self) -> None:
        await self._monotonic_clock.sleep(_WATCH_PERIOD)

    async def run_once(self) -> None:
        if not self._thread_alive():
            raise WebuiThreadEndedError("the webui's thread has ended while the node runs")
