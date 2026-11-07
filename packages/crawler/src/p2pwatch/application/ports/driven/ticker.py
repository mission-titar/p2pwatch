"""Progress, injectable: ``Ticker`` calls back beside a long synchronous operation."""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Protocol


class Operation[T](Protocol):
    def __call__(self) -> T: ...


class Tick(Protocol):
    def __call__(self, *, elapsed: timedelta) -> None: ...


class Ticker(ABC):
    """Calls back every period while a synchronous operation holds the thread that runs it."""

    @abstractmethod
    def run[T](self, operation: Operation[T], *, tick: Tick, period: timedelta) -> T:
        """Runs ``operation`` and returns what it returns, calling ``tick`` a period or more after
        the previous call with the time since the run began; never once ``run`` has returned."""
