import asyncio
from collections.abc import Sequence
from typing import Protocol

from p2pwatch.application.ports.driven.state_owner import StateOwner


class WorksAdder(Protocol):
    def __call__(self, state: object, /) -> None: ...


def _add_nothing(state: object, /) -> None:
    """Adds no work."""


class FakeStateOwner(StateOwner):
    """Its state an ``object()`` built anew at each restart, then handed to ``add_works``; its
    first ``raising`` restarts raise in turn, after their works if ``raising_after_adding``."""

    def __init__(
        self,
        name: str = "owner",
        *,
        add_works: WorksAdder = _add_nothing,
        raising: Sequence[Exception] = (),
        raising_after_adding: bool = False,
    ) -> None:
        self._name = name
        self._add_works = add_works
        self._raising = list(raising)
        self._raising_after_adding = raising_after_adding
        self.state = object()
        self.attempts: list[float] = []

    def __str__(self) -> str:
        return self._name

    async def restart(self) -> None:
        self.attempts.append(asyncio.get_running_loop().time())  # each attempt's loop time
        if self._raising and not self._raising_after_adding:
            raise self._raising.pop(0)
        self.state = object()
        self._add_works(self.state)
        if self._raising:
            raise self._raising.pop(0)
