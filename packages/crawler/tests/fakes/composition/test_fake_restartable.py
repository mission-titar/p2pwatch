from collections.abc import Sequence
from datetime import timedelta

import pytest

from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.work import SupervisedWork, Work
from tests.contracts.application.ports.driven.restartable_contract import RestartableContract
from tests.fakes.composition.fake_restartable import FakeRestartable


class _Over(Work):
    """A work over one state, never run."""

    def __init__(self, state: object) -> None:
        self.state = state

    def __str__(self) -> str:
        return "work over a state"

    async def wait_for_next_turn(self) -> None:
        """Never awaited."""

    async def run_once(self) -> None:
        """Never awaited."""


def _works_over(state: object, /) -> Sequence[SupervisedWork]:
    return [SupervisedWork(work=_Over(state), time_limit=timedelta(minutes=1), dependencies=())]


class TestFakeRestartable(RestartableContract):
    @pytest.fixture
    def restartable(self) -> FakeRestartable:
        return FakeRestartable(works_over=_works_over)

    def state_of(self, restartable: Restartable[object]) -> object:
        assert isinstance(restartable, FakeRestartable)
        return restartable.state

    def state_under(self, works: Sequence[object]) -> object:
        [supervised] = works
        assert isinstance(supervised, SupervisedWork)
        assert isinstance(supervised.work, _Over)
        return supervised.work.state


@pytest.mark.asyncio
async def test_a_rebuild_raises_each_of_its_errors_in_turn_then_rebuilds() -> None:
    restartable = FakeRestartable(errors=[LookupError("first"), LookupError("second")])
    first = restartable.state

    for message in ("first", "second"):
        with pytest.raises(LookupError, match=message):
            await restartable.rebuild()
        assert restartable.state is first
    await restartable.rebuild()

    assert restartable.state is not first
    assert len(restartable.rebuilt_at) == 3
    assert str(restartable) == "client amuled"
