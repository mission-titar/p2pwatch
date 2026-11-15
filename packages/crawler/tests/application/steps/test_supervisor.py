"""The supervisor takes each work's turns, each after its wait, until the shutdown is requested,
whoever asks for it; the shutdown's bound is armed before the works are cancelled."""

import asyncio

import pytest

from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.work import Work
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore

# Every wait on a work's start is bounded: a work that never starts would hang the test.
_START_BOUND_SECONDS = 1.0


class _LastTurnError(Exception):
    """Raised by the last turn of a ``_CountedWork``, so its test's supervision ends."""


class _CountedWork(Work):
    """Notes each wait and each turn, neither of which suspends; its last turn raises."""

    def __init__(self, *, turns: int) -> None:
        self.calls: list[str] = []
        self._turns_left = turns

    async def wait_for_next_turn(self) -> None:
        self.calls.append("wait")

    async def run_once(self) -> None:
        self.calls.append("turn")
        self._turns_left -= 1
        if self._turns_left == 0:
            raise _LastTurnError


class _BlockedWork(Work):
    """A work whose first turn never ends on its own; it notes its cancellation in ``events``."""

    def __init__(self, name: str, *, events: list[str]) -> None:
        self._name = name
        self._events = events
        self.started = asyncio.Event()

    async def wait_for_next_turn(self) -> None:
        """Waits for nothing: the first turn starts at once."""

    async def run_once(self) -> None:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self._events.append(f"{self._name} cancelled")
            raise


class _RaisingWork(Work):
    """A work whose first turn raises, as a bug would."""

    async def wait_for_next_turn(self) -> None:
        """Waits for nothing: the first turn starts at once."""

    async def run_once(self) -> None:
        raise ValueError("a turn raised")


class _WorkStoppingTheNode(Work):
    """Requests the shutdown at each turn, as the webui's restart button does; never waits."""

    def __init__(self) -> None:
        self.run_state = FakeRunStateStore()
        self.turns = 0

    async def wait_for_next_turn(self) -> None:
        """Waits for nothing: each turn starts at once."""

    async def run_once(self) -> None:
        self.turns += 1
        self.run_state.set_shutdown_requested()


@pytest.mark.asyncio
async def test_each_turn_comes_after_its_wait_and_an_exception_in_a_turn_ends_the_supervision() -> (
    None
):
    work = _CountedWork(turns=2)
    supervision = Supervisor(run_state_reader=FakeRunStateStore()).supervise(
        [work], arm_shutdown_bound=lambda: None
    )

    with pytest.RaisesGroup(_LastTurnError):
        await asyncio.wait_for(supervision, 1.0)

    assert work.calls == ["wait", "turn", "wait", "turn"]


@pytest.mark.asyncio
async def test_a_turn_that_never_suspends_still_lets_other_tasks_run_after_it() -> None:
    work = _CountedWork(turns=3)
    supervision = asyncio.create_task(
        Supervisor(run_state_reader=FakeRunStateStore()).supervise(
            [work], arm_shutdown_bound=lambda: None
        )
    )

    await asyncio.sleep(0)  # noqa: TID251  # the supervisor starts the work's task
    await asyncio.sleep(0)  # noqa: TID251  # the work takes its first turn, then lets this test run

    assert work.calls == ["wait", "turn"]
    with pytest.RaisesGroup(_LastTurnError):
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
    await asyncio.wait_for(search.started.wait(), _START_BOUND_SECONDS)
    await asyncio.wait_for(status.started.wait(), _START_BOUND_SECONDS)

    run_state.set_shutdown_requested()  # as the webui's restart button does: no signal involved
    await asyncio.wait_for(supervision, 1.0)

    assert events[0] == "armed"
    assert sorted(events[1:]) == ["search cancelled", "status cancelled"]


@pytest.mark.asyncio
async def test_a_turn_that_raises_escapes_as_an_exception_group_without_arming_the_bound() -> None:
    events: list[str] = []
    status = _BlockedWork("status", events=events)

    supervision = Supervisor(run_state_reader=FakeRunStateStore()).supervise(
        [status, _RaisingWork()], arm_shutdown_bound=lambda: events.append("armed")
    )

    with pytest.RaisesGroup(pytest.RaisesExc(ValueError, match="a turn raised")):
        await asyncio.wait_for(supervision, 1.0)

    assert events == ["status cancelled"]


@pytest.mark.asyncio
async def test_a_shutdown_requested_before_the_start_starts_no_turn() -> None:
    run_state = FakeRunStateStore()
    run_state.set_shutdown_requested()
    status = _BlockedWork("status", events=[])
    supervisor = Supervisor(run_state_reader=run_state)

    await asyncio.wait_for(supervisor.supervise([status], arm_shutdown_bound=lambda: None), 1)

    assert not status.started.is_set()


@pytest.mark.asyncio
async def test_a_shutdown_requested_during_a_turn_lets_that_work_take_no_further_turn() -> None:
    work = _WorkStoppingTheNode()
    supervisor = Supervisor(run_state_reader=work.run_state)

    await asyncio.wait_for(supervisor.supervise([work], arm_shutdown_bound=lambda: None), 1)

    assert work.turns == 1
