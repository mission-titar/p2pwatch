"""The webui's liveness, a work: a turn each status period over its thread, which serves until it
falls, a fallen thread a bug (spec v5 lot 4, D4)."""

from typing import Protocol

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.status_reading import STATUS_PERIOD


class WebuiThreadAlive(Protocol):
    def __call__(self) -> bool: ...


class WebuiFallen(Exception):
    """The webui's thread ended while the node runs."""


class WebuiLiveness(Work):
    """Looks at the webui's thread each status period, its first look a period after its start."""

    def __init__(self, *, thread_alive: WebuiThreadAlive, monotonic_clock: MonotonicClock) -> None:
        self._thread_alive = thread_alive
        self._monotonic_clock = monotonic_clock

    def __str__(self) -> str:
        return "webui"

    async def wait_for_next_turn(self) -> None:
        await self._monotonic_clock.sleep(STATUS_PERIOD)

    async def run_once(self) -> None:
        if not self._thread_alive():
            raise WebuiFallen("its thread has ended")
