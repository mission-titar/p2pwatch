import asyncio
from collections.abc import Iterable, Sequence
from typing import Protocol

from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.work import SupervisedWork


# The works over ``state``, the one a rebuild just built.
class WorksOver(Protocol):
    def __call__(self, state: object, /) -> Sequence[SupervisedWork]: ...


def _no_work(state: object, /) -> Sequence[SupervisedWork]:
    return ()


class FakeRestartable(Restartable[SupervisedWork]):
    """Its state an ``object()``, built anew at each rebuild, which hands back ``works_over`` it;
    a rebuild raises the next of ``errors`` first, until they run out."""

    def __init__(
        self,
        name: str = "client amuled",
        *,
        works_over: WorksOver = _no_work,
        errors: Iterable[Exception] = (),
    ) -> None:
        self._name = name
        self._works_over = works_over
        self._errors = iter(errors)
        self.state = object()
        self.rebuilt_at: list[float] = []  # the loop's time at each rebuild, one that raised too

    def __str__(self) -> str:
        return self._name

    async def rebuild(self) -> Sequence[SupervisedWork]:
        self.rebuilt_at.append(asyncio.get_running_loop().time())
        error = next(self._errors, None)
        if error is not None:
            raise error
        self.state = object()
        return self._works_over(self.state)
