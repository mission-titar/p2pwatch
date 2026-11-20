"""The supervisor takes each work's turns, each after its wait, until the shutdown is requested,
whoever asks for it; the shutdown's bound is armed before the works are cancelled.

A turn that raises fails alone: an expected error is one warning line, any other exception is a
bug, logged with its trace, and its work's next turn comes at least 60 s later. A turn still
running at its work's time limit is cut, and counts as a bug of its object, which three in a row
rebuild. The timed tests share one simulated time, on the virtual-time loop.
"""

import asyncio
import itertools
from collections.abc import Iterable
from datetime import timedelta

import pytest

from p2pwatch.application.steps.supervisor import (
    WAIT_AFTER_A_BUG,
    ShutdownBoundArmer,
    Supervisor,
)
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.domain.client_errors import SearchFailedError
from tests.fakes.adapters.driven.fake_blocking_monotonic_clock import FakeBlockingMonotonicClock
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.composition.fake_restartable_builder import FakeRestartableBuilder
from tests.support.virtual_time import VirtualLoop

# Every wait on a work's start is bounded: a work that never starts would hang the test.
_START_BOUND_SECONDS = 1.0
_AFTER_A_BUG = WAIT_AFTER_A_BUG.total_seconds()
# Longer than any of these tests: a turn is cut only where a test sets a shorter limit.
_DAY = timedelta(days=1)


class _CountedWork(Work):
    """Notes each wait and each turn, neither of which suspends; its last turn requests the
    shutdown."""

    def __init__(self, *, turns: int) -> None:
        self.calls: list[str] = []
        self.run_state = FakeRunStateStore()
        self._turns_left = turns

    def __str__(self) -> str:
        return "counted work"

    async def wait_for_next_turn(self) -> None:
        self.calls.append("wait")

    async def run_once(self) -> None:
        self.calls.append("turn")
        self._turns_left -= 1
        if self._turns_left == 0:
            self.run_state.set_shutdown_requested()


class _TimedWork(Work):
    """Waits ``wait_seconds`` before each turn, the first included, and notes when each turn
    starts; each turn raises the next of ``errors``, until they run out."""

    def __init__(self, name: str, *, wait_seconds: float, errors: Iterable[Exception] = ()) -> None:
        self._name = name
        self._wait_seconds = wait_seconds
        self._errors = iter(errors)
        self.turns: list[float] = []

    def __str__(self) -> str:
        return self._name

    async def wait_for_next_turn(self) -> None:
        await asyncio.sleep(self._wait_seconds)  # noqa: TID251

    async def run_once(self) -> None:
        self.turns.append(asyncio.get_running_loop().time())
        error = next(self._errors, None)
        if error is not None:
            raise error


class _WorkRaisingFromAKeyError(Work):
    """Waits a second, then its turn raises a ``RuntimeError`` from the ``KeyError`` it was
    handling, as a mapping bug would."""

    def __init__(self) -> None:
        self.missing = KeyError("channels")

    def __str__(self) -> str:
        return "status reading amuled"

    async def wait_for_next_turn(self) -> None:
        await asyncio.sleep(1.0)  # noqa: TID251

    async def run_once(self) -> None:
        try:
            raise self.missing
        except KeyError as missing:
            raise RuntimeError("a mapping bug") from missing


class _BlockedWork(Work):
    """A work whose first turn never ends on its own; it notes its cancellation in ``events``."""

    def __init__(self, name: str, *, events: list[str]) -> None:
        self._name = name
        self._events = events
        self.started = asyncio.Event()

    def __str__(self) -> str:
        return self._name

    async def wait_for_next_turn(self) -> None:
        """Waits for nothing: the first turn starts at once."""

    async def run_once(self) -> None:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self._events.append(f"{self._name} cancelled")
            raise


class _HungWork(Work):
    """A work whose turns never end on their own; it notes when each turn starts and when it is
    cut."""

    def __init__(self) -> None:
        self.turns: list[float] = []
        self.cut_at: list[float] = []

    def __str__(self) -> str:
        return "hung work"

    async def wait_for_next_turn(self) -> None:
        """Waits for nothing: each turn starts at once."""

    async def run_once(self) -> None:
        loop = asyncio.get_running_loop()
        self.turns.append(loop.time())
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cut_at.append(loop.time())
            raise


class _WorkWhoseWaitRaises(Work):
    """A work whose wait raises, as a bug in it would."""

    def __str__(self) -> str:
        return "work whose wait raises"

    async def wait_for_next_turn(self) -> None:
        raise ValueError("a wait raised")

    async def run_once(self) -> None:
        """Never reached: its wait raises first."""


class _WorkStoppingTheNode(Work):
    """Requests the shutdown at each turn, as the webui's restart button does; never waits."""

    def __init__(self) -> None:
        self.run_state = FakeRunStateStore()
        self.turns = 0

    def __str__(self) -> str:
        return "work stopping the node"

    async def wait_for_next_turn(self) -> None:
        """Waits for nothing: each turn starts at once."""

    async def run_once(self) -> None:
        self.turns += 1
        self.run_state.set_shutdown_requested()


def _supervised(*works: Work, time_limit: timedelta = _DAY) -> list[SupervisedWork]:
    """Each of ``works`` with ``time_limit``."""
    return [SupervisedWork(work=work, time_limit=time_limit) for work in works]


def _supervisor(run_state: FakeRunStateStore) -> Supervisor:
    """A supervisor for the tests where no turn meets a bug or its time limit: its clock's sleep
    never ends."""
    return Supervisor(
        run_state_reader=run_state,
        monotonic_clock=FakeBlockingMonotonicClock(),
        logger=FakeLogger(),
    )


async def _supervise(
    supervisor: Supervisor,
    /,
    *works: SupervisedWork,
    arm_shutdown_bound: ShutdownBoundArmer = lambda: None,
) -> FakeRestartableBuilder:
    """Takes the turns of ``works``, those of one object ``supervisor`` built first, until the
    shutdown is requested; returns that object's builder."""
    builder = FakeRestartableBuilder(works_over=lambda _state: works)
    await supervisor.build_first(builder)
    await supervisor.supervise(arm_shutdown_bound=arm_shutdown_bound)
    return builder


def _supervise_until(
    loop: VirtualLoop,
    *works: Work,
    seconds: float,
    logger: FakeLogger | None = None,
    time_limit: timedelta = _DAY,
) -> FakeRestartableBuilder:
    """Takes the turns of ``works`` on ``loop``, each with ``time_limit``, the works of one object,
    until the shutdown requested at ``seconds``; returns that object's builder."""
    run_state = FakeRunStateStore()
    loop.call_later(seconds, run_state.set_shutdown_requested)
    supervisor = Supervisor(
        run_state_reader=run_state,
        monotonic_clock=FakeLoopMonotonicClock(loop),
        logger=logger or FakeLogger(),
    )
    return loop.run_until_complete(
        _supervise(supervisor, *_supervised(*works, time_limit=time_limit))
    )


@pytest.mark.asyncio
async def test_each_turn_comes_after_its_wait_the_first_included() -> None:
    work = _CountedWork(turns=2)

    await asyncio.wait_for(
        _supervise(_supervisor(work.run_state), *_supervised(work)),
        1.0,
    )

    assert work.calls == ["wait", "turn", "wait", "turn"]


@pytest.mark.asyncio
async def test_a_turn_that_never_suspends_still_lets_other_tasks_run_after_it() -> None:
    work = _CountedWork(turns=3)
    supervision = asyncio.create_task(_supervise(_supervisor(work.run_state), *_supervised(work)))

    await asyncio.sleep(0)  # noqa: TID251  # the supervisor starts the work's task
    await asyncio.sleep(0)  # noqa: TID251  # the work takes its first turn, then lets this test run

    assert work.calls == ["wait", "turn"]
    await asyncio.wait_for(supervision, 1.0)


def test_it_takes_the_turns_of_the_works_of_each_object_it_built_first(
    virtual_loop: VirtualLoop,
) -> None:
    search = _TimedWork("search 'keroro' amuled kad", wait_seconds=10.0)
    watch = _TimedWork("webui", wait_seconds=10.0)
    builders = [
        FakeRestartableBuilder("client amuled", works_over=lambda _state: _supervised(search)),
        FakeRestartableBuilder("webui", works_over=lambda _state: _supervised(watch)),
    ]
    run_state = FakeRunStateStore()
    virtual_loop.call_later(35.0, run_state.set_shutdown_requested)
    supervisor = Supervisor(
        run_state_reader=run_state,
        monotonic_clock=FakeLoopMonotonicClock(virtual_loop),
        logger=FakeLogger(),
    )

    async def build_each_then_supervise() -> None:
        for builder in builders:
            await supervisor.build_first(builder)
        await supervisor.supervise(arm_shutdown_bound=lambda: None)

    virtual_loop.run_until_complete(build_each_then_supervise())

    assert search.turns == watch.turns == [10.0, 20.0, 30.0]


def test_an_expected_error_fails_its_turn_alone_in_one_warning_line(
    virtual_loop: VirtualLoop,
) -> None:
    logger = FakeLogger()
    refused = _TimedWork(
        "search 'keroro' amuled kad",
        wait_seconds=10.0,
        errors=itertools.repeat(SearchFailedError("amuled refused the search")),
    )
    searching = _TimedWork("search 'keroro' amuled ed2k", wait_seconds=10.0)

    _supervise_until(virtual_loop, refused, searching, seconds=35.0, logger=logger)

    # Neither waits longer than its own wait: an expected error is no bug.
    assert refused.turns == searching.turns == [10.0, 20.0, 30.0]
    message = "search 'keroro' amuled kad: amuled refused the search"
    assert logger.lines == [LoggedLine(level="warning", message=message)] * 3


def test_a_bug_fails_its_turn_alone_logged_with_its_trace(virtual_loop: VirtualLoop) -> None:
    logger = FakeLogger()
    bug = KeyError("channels")
    broken = _TimedWork("status reading amuled", wait_seconds=1.0, errors=itertools.repeat(bug))
    searching = _TimedWork("search 'keroro' amuled ed2k", wait_seconds=30.0)

    _supervise_until(virtual_loop, broken, searching, seconds=100.0, logger=logger)

    assert searching.turns == [30.0, 60.0, 90.0]
    assert broken.turns == [1.0, 61.0]
    bug_line = LoggedLine(level="error", message="bug in status reading amuled", error=bug)
    assert logger.lines == [bug_line, bug_line]


def test_a_bug_is_logged_with_the_exception_it_was_raised_from(virtual_loop: VirtualLoop) -> None:
    logger = FakeLogger()
    broken = _WorkRaisingFromAKeyError()

    _supervise_until(virtual_loop, broken, seconds=30.0, logger=logger)

    [bug_line] = logger.lines
    assert bug_line.message == "bug in status reading amuled"
    assert bug_line.error is not None
    assert bug_line.error.__cause__ is broken.missing


def test_two_turns_of_a_work_meeting_a_bug_at_once_are_never_closer_than_60_s(
    virtual_loop: VirtualLoop,
) -> None:
    # Its own wait is 1 s: without the 60 s after a bug, its turns would follow each other.
    broken = _TimedWork("broken", wait_seconds=1.0, errors=itertools.repeat(RuntimeError("bug")))

    _supervise_until(virtual_loop, broken, seconds=2.0 + 2 * _AFTER_A_BUG)

    # Its third bug in a row rebuilds its object, whose works take their first turn afresh.
    assert broken.turns[:3] == [1.0, 1.0 + _AFTER_A_BUG, 1.0 + 2 * _AFTER_A_BUG]


def test_after_a_bug_a_wait_of_its_own_longer_than_60_s_is_waited_alone(
    virtual_loop: VirtualLoop,
) -> None:
    broken_once = _TimedWork("broken once", wait_seconds=100.0, errors=[RuntimeError("bug")])

    _supervise_until(virtual_loop, broken_once, seconds=250.0)

    # The later of the two waits, never their sum.
    assert broken_once.turns == [100.0, 200.0]


def test_a_turn_still_running_at_its_time_limit_is_cut_as_a_bug_and_its_work_goes_on(
    virtual_loop: VirtualLoop,
) -> None:
    logger = FakeLogger()
    hung = _HungWork()
    stop_at = 2 * (30.0 + _AFTER_A_BUG) + 1.0

    _supervise_until(
        virtual_loop, hung, seconds=stop_at, logger=logger, time_limit=timedelta(seconds=30)
    )

    # Each turn cut at 30 s, then the 60 s after a bug before the next; the last one at the stop.
    assert hung.turns == [0.0, 30.0 + _AFTER_A_BUG, 2 * (30.0 + _AFTER_A_BUG)]
    assert hung.cut_at == [30.0, 30.0 + _AFTER_A_BUG + 30.0, stop_at]
    cut_line = LoggedLine(level="error", message="hung work: past its time limit of 30 s")
    assert logger.lines == [cut_line, cut_line]


def test_after_a_turn_that_worked_the_work_waits_its_own_wait_alone_again(
    virtual_loop: VirtualLoop,
) -> None:
    broken_once = _TimedWork("broken once", wait_seconds=10.0, errors=[RuntimeError("bug")])

    _supervise_until(virtual_loop, broken_once, seconds=95.0)

    assert broken_once.turns == [
        10.0,
        10.0 + _AFTER_A_BUG,
        20.0 + _AFTER_A_BUG,
        30.0 + _AFTER_A_BUG,
    ]


@pytest.mark.parametrize(
    "errors",
    [(), itertools.repeat(SearchFailedError("amuled refused the search"))],
    ids=["turns that worked", "turns that met an expected error"],
)
def test_turns_without_a_bug_rebuild_nothing(
    virtual_loop: VirtualLoop, *, errors: Iterable[Exception]
) -> None:
    search = _TimedWork("search 'keroro' amuled kad", wait_seconds=10.0, errors=errors)

    client = _supervise_until(virtual_loop, search, seconds=35.0)

    assert search.turns == [10.0, 20.0, 30.0]
    assert client.rebuilds() == 0


def test_turns_cut_at_their_time_limit_count_as_bugs_three_in_a_row_rebuilding_their_object(
    virtual_loop: VirtualLoop,
) -> None:
    hung = _HungWork()
    third_cut = 3 * 30.0 + 2 * _AFTER_A_BUG

    client = _supervise_until(
        virtual_loop, hung, seconds=third_cut + 61.0, time_limit=timedelta(seconds=30)
    )

    assert hung.cut_at[:3] == [30.0, 30.0 + _AFTER_A_BUG + 30.0, third_cut]
    assert client.built_at == [0.0, third_cut + 60.0]  # a minute after the third


@pytest.mark.asyncio
async def test_a_stop_without_a_signal_arms_the_bound_before_cancelling_every_work() -> None:
    events: list[str] = []
    run_state = FakeRunStateStore()
    search, status = _BlockedWork("search", events=events), _BlockedWork("status", events=events)
    supervision = asyncio.create_task(
        _supervise(
            _supervisor(run_state),
            *_supervised(search, status),
            arm_shutdown_bound=lambda: events.append("armed"),
        )
    )
    await asyncio.wait_for(search.started.wait(), _START_BOUND_SECONDS)
    await asyncio.wait_for(status.started.wait(), _START_BOUND_SECONDS)

    run_state.set_shutdown_requested()  # as the webui's restart button does: no signal involved
    await asyncio.wait_for(supervision, 1.0)

    assert events[0] == "armed"
    assert sorted(events[1:]) == ["search cancelled", "status cancelled"]


@pytest.mark.asyncio
async def test_a_wait_that_raises_escapes_as_an_exception_group_without_arming_the_bound() -> None:
    events: list[str] = []
    status = _BlockedWork("status", events=events)

    supervision = _supervise(
        _supervisor(FakeRunStateStore()),
        *_supervised(status, _WorkWhoseWaitRaises()),
        arm_shutdown_bound=lambda: events.append("armed"),
    )

    with pytest.RaisesGroup(pytest.RaisesExc(ValueError, match="a wait raised")):
        await asyncio.wait_for(supervision, 1.0)

    assert events == ["status cancelled"]


@pytest.mark.asyncio
async def test_a_shutdown_requested_before_the_start_starts_no_turn() -> None:
    run_state = FakeRunStateStore()
    run_state.set_shutdown_requested()
    status = _BlockedWork("status", events=[])

    await asyncio.wait_for(_supervise(_supervisor(run_state), *_supervised(status)), 1)

    assert not status.started.is_set()


@pytest.mark.asyncio
async def test_a_shutdown_requested_during_a_turn_lets_that_work_take_no_further_turn() -> None:
    work = _WorkStoppingTheNode()

    await asyncio.wait_for(_supervise(_supervisor(work.run_state), *_supervised(work)), 1)

    assert work.turns == 1
