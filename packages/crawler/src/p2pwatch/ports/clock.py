"""Time, injectable: ``WallClock`` stamps, ``MonotonicClock`` measures every interval and deadline
kept in memory."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, overload


class WallClock(Protocol):
    """The UTC time of day, aware: every stamp a row, an event or a display carries."""

    def now(self) -> datetime: ...


@dataclass(frozen=True, order=True)
class MonotonicInstant:
    """Never persisted nor displayed: its origin changes with each process. Its arithmetic and its
    ordering refuse a ``datetime``, for mypy and at run time."""

    nanoseconds: int

    def __add__(self, duration: timedelta) -> "MonotonicInstant":
        return MonotonicInstant(self.nanoseconds + _nanoseconds(duration))

    @overload
    def __sub__(self, other: "MonotonicInstant") -> timedelta: ...
    @overload
    def __sub__(self, other: timedelta) -> "MonotonicInstant": ...
    def __sub__(self, other: "MonotonicInstant | timedelta") -> "timedelta | MonotonicInstant":
        if isinstance(other, MonotonicInstant):
            return timedelta(microseconds=(self.nanoseconds - other.nanoseconds) / 1000)
        return MonotonicInstant(self.nanoseconds - _nanoseconds(other))


def _nanoseconds(duration: timedelta) -> int:
    return duration // timedelta(microseconds=1) * 1000


class MonotonicClock(Protocol):
    """Every interval and deadline kept in memory: a step of the wall clock never moves it."""

    def now(self) -> MonotonicInstant: ...

    async def sleep(self, duration: timedelta) -> None: ...
