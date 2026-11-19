from collections.abc import Sequence
from datetime import timedelta

import pytest

from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.work import SupervisedWork, Work
from tests.contracts.application.ports.driven.restartable_builder_contract import (
    RestartableBuilderContract,
)
from tests.fakes.composition.fake_restartable import FakeRestartable
from tests.fakes.composition.fake_restartable_builder import FakeRestartableBuilder


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


class TestFakeRestartableBuilder(RestartableBuilderContract):
    @pytest.fixture
    def restartable_builder(self) -> FakeRestartableBuilder:
        return FakeRestartableBuilder(works_over=_works_over)

    def state_of(self, restartable: Restartable[object]) -> object:
        assert isinstance(restartable, FakeRestartable)
        return restartable.state

    def state_reached(self, restartable: Restartable[object]) -> object:
        [supervised] = restartable.works()
        assert isinstance(supervised, SupervisedWork)
        assert isinstance(supervised.work, _Over)
        return supervised.work.state


@pytest.mark.asyncio
async def test_each_build_after_the_first_raises_each_of_its_errors_in_turn_then_builds() -> None:
    builder = FakeRestartableBuilder(rebuild_errors=[LookupError("first"), LookupError("second")])
    await builder.build()

    for message in ("first", "second"):
        with pytest.raises(LookupError, match=message):
            await builder.build()
    await builder.build()

    assert (len(builder.built), builder.rebuilds()) == (2, 3)
    assert str(builder) == "client amuled"


@pytest.mark.asyncio
async def test_each_object_notes_its_closes_under_its_builder_s_name_raising_its_error() -> None:
    closed: list[str] = []
    refused = RuntimeError("would not join")
    restartable = await FakeRestartableBuilder("webui", closed=closed, close_error=refused).build()

    with pytest.raises(RuntimeError):
        await restartable.close()

    assert (restartable.closes, closed) == (1, ["webui"])
