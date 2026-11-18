import asyncio
from collections.abc import Iterable, Sequence
from typing import Protocol

from p2pwatch.application.ports.driven.restartable_builder import RestartableBuilder
from p2pwatch.application.steps.work import SupervisedWork
from tests.fakes.composition.fake_restartable import FakeRestartable


# The works over ``state``, the one a build just made.
class WorksOver(Protocol):
    def __call__(self, state: object, /) -> Sequence[SupervisedWork]: ...


def _no_work(state: object, /) -> Sequence[SupervisedWork]:
    return ()


class FakeRestartableBuilder(RestartableBuilder[FakeRestartable]):
    """Builds a ``FakeRestartable`` over a new ``object()``, with ``works_over`` it; each rebuild,
    the first build excepted, raises the next of ``rebuild_errors`` first, until they run out.
    Each object it builds notes its closes under its name in ``closed``, raising ``close_error``."""

    def __init__(
        self,
        name: str = "client amuled",
        *,
        works_over: WorksOver = _no_work,
        rebuild_errors: Iterable[Exception] = (),
        closed: list[str] | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self._name = name
        self._works_over = works_over
        self._rebuild_errors = iter(rebuild_errors)
        self._close_error = close_error
        self.closed: list[str] = [] if closed is None else closed
        self.built: list[FakeRestartable] = []
        self.built_at: list[float] = []  # the loop's time at each build, one that raised too

    def __str__(self) -> str:
        return self._name

    async def build(self) -> FakeRestartable:
        self.built_at.append(asyncio.get_running_loop().time())
        error = next(self._rebuild_errors, None) if self.built else None
        if error is not None:
            raise error
        state = object()
        restartable = FakeRestartable(
            state=state,
            works=self._works_over(state),
            name=self._name,
            closed=self.closed,
            close_error=self._close_error,
        )
        self.built.append(restartable)
        return restartable

    def rebuilds(self) -> int:
        """How many builds came after the first, one that raised included."""
        return max(len(self.built_at) - 1, 0)
