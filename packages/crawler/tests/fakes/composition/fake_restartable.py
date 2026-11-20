from collections.abc import Sequence

from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.work import SupervisedWork


class FakeRestartable(Restartable[SupervisedWork]):
    """Its state an ``object()`` and the works over it; each close is counted and noted under
    ``name`` in ``closed``, then raises ``close_error`` if one is given."""

    def __init__(
        self,
        *,
        state: object,
        works: Sequence[SupervisedWork],
        name: str,
        closed: list[str],
        close_error: Exception | None,
    ) -> None:
        self.state = state
        self._works = tuple(works)
        self._name = name
        self._closed = closed
        self._close_error = close_error
        self.closes = 0

    def works(self) -> Sequence[SupervisedWork]:
        return self._works

    async def close(self) -> None:
        self.closes += 1
        self._closed.append(self._name)
        if self._close_error is not None:
            raise self._close_error
