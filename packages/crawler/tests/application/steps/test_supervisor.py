"""Each work's turns run until the stop, whoever asks; a turn that raises fails alone, a bug's next
turn waiting at least the floor; the bound is armed before the works unwind.

The timed tests share one simulated time, on the virtual-time loop.
"""

import asyncio
from collections.abc import Sequence

import pytest

from p2pwatch.application.steps.supervisor import FLOOR_AFTER_A_BUG, Supervisor
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.client_errors import SearchFailedError
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.support.virtual_time import VirtualLoop

_FLOOR = FLOOR_AFTER_A_BUG.total_seconds()


class _PacedWork(Work):
    """Waits ``wait_seconds`` before each turn, the first included, and records when each turn
    starts; its first ``raising`` turns raise their error in turn, every one when ``always``."""

    def __init__(
        self,
        name: str,
        *,
        wait_seconds: float,
        raising: Sequence[Exception] = (),
        always: bool = False,
    ) -> None:
        self._name = name
        self._wait_seconds = wait_seconds
        self._raising = list(raising)
        self._always = always
        self.turns: list[float] = []

    def __str__(self) -> str:
        return self._name

    async def wait_for_next_turn(self) -> None:
        await asyncio.sleep(self._wait_seconds)  # noqa: TID251

    async def run_once(self) -> None:
        self.turns.append(asyncio.get_running_loop().time())
        if not self._raising:
            return
        if self._always:
            raise self._raising[0]
        raise self._raising.pop(0)


class _RaisingWait(Work):
    """A work whose wait raises."""

    def __str__(self) -> str:
        return "raising wait"

    async def wait_for_next_turn(self) -> None:
        raise LookupError("no wait")

    async def run_once(self) -> None:
        """Never reached."""


class _CountedWork(Work):
    """Counts its turns, neither its wait nor its turn suspending."""

    def __init__(self) -> None:
        self.turns = 0

    def __str__(self) -> str:
        return "counted"

    async def wait_for_next_turn(self) -> None:
        """Waits for nothing."""

    async def run_once(self) -> None:
        self.turns += 1


class _BlockedWork(Work):
    """A work whose first turn never ends on its own, and records its cancellation."""

    def __init__(self, name: str, *, events: list[str]) -> None:
        self._name = name
        self._events = events
        self.started = asyncio.Event()

    def __str__(self) -> str:
        return self._name

    async def wait_for_next_turn(self) -> None:
        """Waits for nothing."""

    async def run_once(self) -> None:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self._events.append(f"{self._name} cancelled")
            raise


def _supervisor(*, run_state: FakeRunStateStore, logger: FakeLogger | None = None) -> Supervisor:
    """A supervisor on a clock whose sleeps return at once, for the tests that read no time."""
    return Supervisor(
        run_state_reader=run_state,
        monotonic_clock=FakeTime().monotonic,
        logger=logger or FakeLogger(),
    )


def _supervise_until(
    loop: VirtualLoop, *works: Work, seconds: float, logger: FakeLogger | None = None
) -> None:
    run_state = FakeRunStateStore()
    loop.call_later(seconds, run_state.set_shutdown_requested)
    supervisor = Supervisor(
        run_state_reader=run_state,
        monotonic_clock=FakeLoopMonotonicClock(loop),
        logger=logger or FakeLogger(),
    )
    loop.run_until_complete(supervisor.supervise(works, arm_shutdown_bound=lambda: None))


def test_each_turn_follows_its_wait_the_first_included(virtual_loop: VirtualLoop) -> None:
    work = _PacedWork("paced", wait_seconds=10.0)
    _supervise_until(virtual_loop, work, seconds=35.0)
    assert work.turns == [10.0, 20.0, 30.0]


def test_a_declared_failure_fails_its_turn_alone_logged_in_one_line(
    virtual_loop: VirtualLoop,
) -> None:
    logger = FakeLogger()
    failing = _PacedWork(
        "kad search", wait_seconds=10.0, raising=[SearchFailedError("refused")], always=True
    )
    healthy = _PacedWork("ed2k search", wait_seconds=10.0)

    _supervise_until(virtual_loop, failing, healthy, seconds=35.0, logger=logger)

    assert failing.turns == healthy.turns == [10.0, 20.0, 30.0]  # no floor after it
    assert logger.lines == [LoggedLine(level="warning", message="kad search: refused")] * 3


def test_a_bug_fails_its_turn_alone_logged_with_its_trace(virtual_loop: VirtualLoop) -> None:
    logger = FakeLogger()
    bug = KeyError("channels")
    failing = _PacedWork("kad search", wait_seconds=1.0, raising=[bug], always=True)
    healthy = _PacedWork("ed2k search", wait_seconds=30.0)

    _supervise_until(virtual_loop, failing, healthy, seconds=2 * _FLOOR + 1.0, logger=logger)

    assert healthy.turns == [30.0, 60.0, 90.0, 120.0]
    assert logger.lines == [
        LoggedLine(level="error", message="bug in kad search", error=bug)
    ] * len(failing.turns)


def test_two_turns_of_a_work_raising_a_bug_at_once_are_never_closer_than_the_floor(
    virtual_loop: VirtualLoop,
) -> None:
    # A wait of its own shorter than the floor: without the floor, its turns would follow at once.
    work = _PacedWork("broken", wait_seconds=1.0, raising=[RuntimeError("bug")], always=True)
    _supervise_until(virtual_loop, work, seconds=3 * _FLOOR + 2.0)
    assert work.turns == [1.0, 1.0 + _FLOOR, 1.0 + 2 * _FLOOR, 1.0 + 3 * _FLOOR]


@pytest.mark.parametrize(
    ("wait_seconds", "second_turn_at"),
    [(10.0, 10.0 + _FLOOR), (_FLOOR + 40.0, 2 * (_FLOOR + 40.0))],
)
def test_after_a_bug_the_next_turn_waits_the_later_of_the_floor_and_its_own_wait(
    virtual_loop: VirtualLoop, *, wait_seconds: float, second_turn_at: float
) -> None:
    work = _PacedWork("paced", wait_seconds=wait_seconds, raising=[RuntimeError("bug")])
    _supervise_until(virtual_loop, work, seconds=second_turn_at + 1.0)
    assert work.turns == [wait_seconds, second_turn_at]


def test_a_turn_after_a_success_waits_its_own_wait_alone(virtual_loop: VirtualLoop) -> None:
    work = _PacedWork("paced", wait_seconds=10.0, raising=[RuntimeError("bug")])
    _supervise_until(virtual_loop, work, seconds=10.0 + _FLOOR + 25.0)
    assert work.turns == [10.0, 10.0 + _FLOOR, 20.0 + _FLOOR, 30.0 + _FLOOR]


@pytest.mark.asyncio
async def test_a_turn_that_never_suspends_yields_the_loop_after_it() -> None:
    work = _CountedWork()
    run_state = FakeRunStateStore()
    supervision = asyncio.create_task(
        _supervisor(run_state=run_state).supervise([work], arm_shutdown_bound=lambda: None)
    )

    await asyncio.sleep(0)  # noqa: TID251  # the supervisor starts the work's task
    await asyncio.sleep(0)  # noqa: TID251  # the work takes its first turn

    assert work.turns == 1
    run_state.set_shutdown_requested()
    await asyncio.wait_for(supervision, 1.0)


@pytest.mark.asyncio
async def test_a_stop_without_a_signal_arms_the_bound_before_cancelling_every_work() -> None:
    events: list[str] = []
    run_state = FakeRunStateStore()
    search, status = _BlockedWork("search", events=events), _BlockedWork("status", events=events)
    supervision = asyncio.create_task(
        _supervisor(run_state=run_state).supervise(
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
async def test_a_wait_that_raises_escapes_as_an_exception_group_without_arming_the_bound() -> None:
    events: list[str] = []
    status = _BlockedWork("status", events=events)

    with pytest.RaisesGroup(LookupError):
        await _supervisor(run_state=FakeRunStateStore()).supervise(
            [status, _RaisingWait()], arm_shutdown_bound=lambda: events.append("armed")
        )

    assert events == ["status cancelled"]
