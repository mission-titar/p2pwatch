"""Each work's turns run until the stop, whoever asks; the bound is armed before they unwind."""

import asyncio

import pytest

from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.work import Work
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore


class _Ended(Exception):
    """Ends a recorded work at its last turn."""


class _RecordedWork(Work):
    """Records its waits and turns, neither suspending, and raises at its last turn."""

    def __init__(self, *, turns: int) -> None:
        self.events: list[str] = []
        self._turns_left = turns

    async def wait_for_next_turn(self) -> None:
        self.events.append("wait")

    async def run_once(self) -> None:
        self.events.append("turn")
        self._turns_left -= 1
        if self._turns_left == 0:
            raise _Ended


class _BlockedWork(Work):
    """A work whose first turn never ends on its own, and records its cancellation."""

    def __init__(self, name: str, *, events: list[str]) -> None:
        self._name = name
        self._events = events
        self.started = asyncio.Event()

    async def wait_for_next_turn(self) -> None:
        """Waits for nothing."""

    async def run_once(self) -> None:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self._events.append(f"{self._name} cancelled")
            raise


@pytest.mark.asyncio
async def test_each_turn_follows_its_wait_the_first_included() -> None:
    work = _RecordedWork(turns=2)

    with pytest.RaisesGroup(_Ended):
        await Supervisor(run_state_reader=FakeRunStateStore()).supervise(
            [work], arm_shutdown_bound=lambda: None
        )

    assert work.events == ["wait", "turn", "wait", "turn"]


@pytest.mark.asyncio
async def test_a_turn_that_never_suspends_yields_the_loop_after_it() -> None:
    work = _RecordedWork(turns=100)
    run_state = FakeRunStateStore()
    supervision = asyncio.create_task(
        Supervisor(run_state_reader=run_state).supervise([work], arm_shutdown_bound=lambda: None)
    )

    await asyncio.sleep(0)  # noqa: TID251  # the supervisor starts the work's task
    await asyncio.sleep(0)  # noqa: TID251  # the work takes its first turn

    assert work.events == ["wait", "turn"]
    run_state.set_shutdown_requested()
    await asyncio.wait_for(supervision, 1.0)


@pytest.mark.asyncio
async def test_a_stop_without_a_signal_arms_the_bound_before_cancelling_every_work() -> None:
    events: list[str] = []
    run_state = FakeRunStateStore()
    search, status = _BlockedWork("search", events=events), _BlockedWork("status", events=events)
    supervision = asyncio.create_task(
        Supervisor(run_state_reader=run_state).supervise(
            [search, status], arm_shutdown_bound=lambda: events.append("armed")
        )
    )
    await search.started.wait()
    await status.started.wait()

    run_state.set_shutdown_requested()  # as the webui's restart button does: no signal involved
    await asyncio.wait_for(supervision, 1.0)

    assert events[0] == "armed"
    assert sorted(events[1:]) == ["search cancelled", "status cancelled"]


@pytest.mark.asyncio
async def test_a_failing_turn_escapes_as_an_exception_group_without_arming_the_bound() -> None:
    events: list[str] = []
    status = _BlockedWork("status", events=events)

    with pytest.RaisesGroup(_Ended):
        await Supervisor(run_state_reader=FakeRunStateStore()).supervise(
            [status, _RecordedWork(turns=1)], arm_shutdown_bound=lambda: events.append("armed")
        )

    assert events == ["status cancelled"]
