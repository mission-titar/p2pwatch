"""Each work's turns run until the stop, whoever asks; a turn that raises or passes its time limit
fails alone, a bug's next turn waiting at least the floor; each turn's outcome is recorded on the
components its work feeds; the bound is armed before the works unwind.

The timed tests share one simulated time, on the virtual-time loop.
"""

import asyncio
from collections.abc import Sequence
from datetime import timedelta
from typing import Protocol

import pytest

from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.application.steps.supervisor import FLOOR_AFTER_A_BUG, SupervisedWork, Supervisor
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.client_errors import SearchFailedError
from p2pwatch.domain.health.component import Component, ComponentLabels
from p2pwatch.domain.health.health_condition import BUGS, Health
from p2pwatch.domain.health.outcome import UNITS_OF_WORK, Outcome
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.status_reading import client_component
from tests.fakes.adapters.driven.fake_blocking_monotonic_clock import FakeBlockingMonotonicClock
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.composition.fake_state_owner import FakeStateOwner
from tests.support.virtual_time import VirtualLoop

_FLOOR = FLOOR_AFTER_A_BUG.total_seconds()
_DAY = timedelta(days=1)
_HALF_MINUTE = timedelta(seconds=30)


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


class _HungWork(Work):
    """A work whose turns never end on their own, and record when each starts and is cut."""

    def __init__(self) -> None:
        self.turns: list[float] = []
        self.cut_at: list[float] = []

    def __str__(self) -> str:
        return "hung"

    async def wait_for_next_turn(self) -> None:
        """Waits for nothing."""

    async def run_once(self) -> None:
        loop = asyncio.get_running_loop()
        self.turns.append(loop.time())
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cut_at.append(loop.time())
            raise


def _component(name: str) -> Component:
    """A component judged on the bugs of the turns alone."""
    return Component(
        name=name, labels=ComponentLabels(client_name=ClientName("amuled")), conditions=(BUGS,)
    )


def _supervised(
    *works: Work, time_limit: timedelta = _DAY, feeds: tuple[Component, ...] = ()
) -> list[SupervisedWork]:
    """Each work feeding ``feeds``, or a component named after it."""
    return [
        SupervisedWork(work=work, time_limit=time_limit, feeds=feeds or (_component(str(work)),))
        for work in works
    ]


def _supervisor(*, run_state: FakeRunStateStore) -> Supervisor:
    """A supervisor whose limits and floors never expire, for the tests that read no time."""
    return Supervisor(
        run_state_reader=run_state,
        monotonic_clock=FakeBlockingMonotonicClock(),
        health_recorder=HealthRecorder(logger=FakeLogger(), subscribers=()),
        restart_policy=RestartPolicy(owners={}, logger=FakeLogger()),
        logger=FakeLogger(),
    )


def _supervise_until(
    loop: VirtualLoop,
    *works: Work,
    seconds: float,
    logger: FakeLogger | None = None,
    health_logger: FakeLogger | None = None,
    time_limit: timedelta = _DAY,
    feeds: tuple[Component, ...] = (),
) -> None:
    run_state = FakeRunStateStore()
    loop.call_later(seconds, run_state.set_shutdown_requested)
    supervisor = Supervisor(
        run_state_reader=run_state,
        monotonic_clock=FakeLoopMonotonicClock(loop),
        health_recorder=HealthRecorder(logger=health_logger or FakeLogger(), subscribers=()),
        restart_policy=RestartPolicy(owners={}, logger=FakeLogger()),
        logger=logger or FakeLogger(),
    )
    loop.run_until_complete(
        supervisor.supervise(
            _supervised(*works, time_limit=time_limit, feeds=feeds),
            arm_shutdown_bound=lambda: None,
        )
    )


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


def test_a_turn_past_its_time_limit_is_cut_as_a_bug_and_its_work_goes_on(
    virtual_loop: VirtualLoop,
) -> None:
    logger = FakeLogger()
    work = _HungWork()

    _supervise_until(
        virtual_loop,
        work,
        seconds=2 * (30.0 + _FLOOR) + 1.0,
        logger=logger,
        time_limit=_HALF_MINUTE,
    )

    # Cut at its limit, then the floor after a bug before the next turn.
    assert work.turns == [0.0, 30.0 + _FLOOR, 2 * (30.0 + _FLOOR)]
    assert work.cut_at == [30.0, 2 * 30.0 + _FLOOR, 2 * (30.0 + _FLOOR) + 1.0]
    message = "hung: past its time limit of 30 s"
    assert logger.lines == [LoggedLine(level="error", message=message)] * 2


def test_a_turn_ending_within_its_time_limit_keeps_its_outcome(virtual_loop: VirtualLoop) -> None:
    logger = FakeLogger()
    work = _PacedWork("paced", wait_seconds=10.0, raising=[SearchFailedError("refused")])
    _supervise_until(virtual_loop, work, seconds=25.0, logger=logger, time_limit=_HALF_MINUTE)
    assert work.turns == [10.0, 20.0]
    assert logger.lines == [LoggedLine(level="warning", message="paced: refused")]


@pytest.mark.parametrize("time_limit", [timedelta(0), timedelta(seconds=-1)])
def test_a_time_limit_that_is_not_positive_is_refused(time_limit: timedelta) -> None:
    with pytest.raises(ValueError, match="time limit"):
        SupervisedWork(work=_CountedWork(), time_limit=time_limit, feeds=(_component("counted"),))


@pytest.mark.parametrize(
    "feeds", [(), (client_component(ClientName("amuled")),)], ids=["none", "no turns read"]
)
def test_a_work_feeding_no_component_reading_its_turns_is_refused(
    feeds: tuple[Component, ...],
) -> None:
    with pytest.raises(ValueError, match="^counted: a component at least expected, each reading"):
        SupervisedWork(work=_CountedWork(), time_limit=_DAY, feeds=feeds)


def test_each_turn_s_outcome_is_recorded_on_every_component_its_work_feeds(
    virtual_loop: VirtualLoop,
) -> None:
    health_logger = FakeLogger()
    work = _PacedWork("kad search", wait_seconds=1.0, raising=[KeyError("channels")], always=True)
    feeds = (_component("search kad"), _component("channel kad"))

    _supervise_until(
        virtual_loop, work, seconds=2 * _FLOOR + 2.0, health_logger=health_logger, feeds=feeds
    )

    assert len(work.turns) == 3
    assert health_logger.lines == [
        LoggedLine(level="warning", message="search kad, bugs: unknown to failing"),
        LoggedLine(level="warning", message="channel kad, bugs: unknown to failing"),
    ]


def test_a_declared_failure_counts_as_no_bug(virtual_loop: VirtualLoop) -> None:
    health_logger = FakeLogger()
    work = _PacedWork("kad search", wait_seconds=10.0, raising=[SearchFailedError("refused")] * 3)
    _supervise_until(virtual_loop, work, seconds=35.0, health_logger=health_logger)
    assert health_logger.lines == [
        LoggedLine(level="info", message="kad search, bugs: unknown to healthy")
    ]


def test_a_turn_past_its_time_limit_is_recorded_as_a_bug(virtual_loop: VirtualLoop) -> None:
    health_logger = FakeLogger()
    _supervise_until(
        virtual_loop,
        _HungWork(),
        seconds=3 * 30.0 + 2 * _FLOOR + 1.0,
        health_logger=health_logger,
        time_limit=_HALF_MINUTE,
    )
    assert health_logger.lines == [
        LoggedLine(level="warning", message="hung, bugs: unknown to failing")
    ]


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
        _supervisor(run_state=run_state).supervise(
            _supervised(work), arm_shutdown_bound=lambda: None
        )
    )

    await asyncio.sleep(0)  # noqa: TID251  # the supervisor starts the work's task
    await asyncio.sleep(0)  # noqa: TID251  # the work's task starts its turn's race
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
            _supervised(search, status), arm_shutdown_bound=lambda: events.append("armed")
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
            _supervised(status, _RaisingWait()), arm_shutdown_bound=lambda: events.append("armed")
        )

    assert events == ["status cancelled"]


class _BugRecorder(Work):
    """Records a bug on a component no work feeds, as a step outside the supervisor would."""

    def __init__(self, *, recorder: HealthRecorder, on: Component) -> None:
        self._recorder = recorder
        self._on = on

    def __str__(self) -> str:
        return "bug recorder"

    async def wait_for_next_turn(self) -> None:
        await asyncio.sleep(10.0)  # noqa: TID251

    async def run_once(self) -> None:
        await self._recorder.record(Outcome.bug("KeyError('x')"), on=self._on, by=UNITS_OF_WORK)


def _broken(component: Component) -> SupervisedWork:
    """A work raising a bug at each turn, its own wait 1 s, so its turns are a floor apart."""
    work = _PacedWork("broken", wait_seconds=1.0, raising=[RuntimeError("bug")], always=True)
    return SupervisedWork(work=work, time_limit=_DAY, feeds=(component,))


def _steady(component: Component) -> SupervisedWork:
    return SupervisedWork(
        work=_PacedWork("steady", wait_seconds=10.0), time_limit=_DAY, feeds=(component,)
    )


class _Build(Protocol):
    def __call__(self) -> list[SupervisedWork]: ...


class _Unowned(Protocol):
    def __call__(self, recorder: HealthRecorder, /) -> Sequence[SupervisedWork]: ...


def _supervise_owned(
    loop: VirtualLoop,
    *,
    build: _Build,
    seconds: float,
    owned: Sequence[Component] = (),
    raising: Sequence[Exception] = (),
    raising_after_adding: bool = False,
    unowned: _Unowned = lambda recorder: (),
    owned_by_another: Sequence[Component] = (),
    logger: FakeLogger | None = None,
    health_logger: FakeLogger | None = None,
) -> tuple[FakeStateOwner, list[list[SupervisedWork]]]:
    """Supervises ``build()``'s works and ``unowned``'s; one owner owns the components the first
    build's works feed, and ``owned``, each of its restarts adding ``build()``'s works again;
    ``unowned``'s feed ``owned_by_another``, another owner's. Returns the owner and each build."""
    builds = [build()]
    run_state = FakeRunStateStore()
    loop.call_later(seconds, run_state.set_shutdown_requested)
    logger = logger or FakeLogger()

    def add_works(_state: object) -> None:
        builds.append(build())
        for supervised in builds[-1]:
            supervisor.add(supervised)

    owner = FakeStateOwner(
        "client", add_works=add_works, raising=raising, raising_after_adding=raising_after_adding
    )
    components = {c for supervised in builds[0] for c in supervised.feeds} | set(owned)
    another = FakeStateOwner("another")
    policy = RestartPolicy(
        owners={**dict.fromkeys(components, owner), **dict.fromkeys(owned_by_another, another)},
        logger=logger,
    )
    recorder = HealthRecorder(logger=health_logger or FakeLogger(), subscribers=(policy,))
    supervisor = Supervisor(
        run_state_reader=run_state,
        monotonic_clock=FakeLoopMonotonicClock(loop),
        health_recorder=recorder,
        restart_policy=policy,
        logger=logger,
    )
    loop.run_until_complete(
        supervisor.supervise([*builds[0], *unowned(recorder)], arm_shutdown_bound=lambda: None)
    )
    return owner, builds


# A broken work's third bug, the first restart: its turns at 1 s, then a floor apart.
_FIRST_RESTART = 1.0 + 2 * _FLOOR


def test_a_bugs_condition_failing_restarts_its_owner_three_times_then_never(
    virtual_loop: VirtualLoop,
) -> None:
    logger = FakeLogger()
    search = _component("search")

    owner, builds = _supervise_owned(
        virtual_loop, build=lambda: [_broken(search)], seconds=20 * _FLOOR, logger=logger
    )

    # Each rebuilt work needs three bugs of its own to fail again.
    assert owner.attempts == [_FIRST_RESTART + n * (1.0 + 2 * _FLOOR) for n in range(3)]
    assert len(builds) == 4
    last = builds[-1][0].work
    assert isinstance(last, _PacedWork)
    assert last.turns[-1] > 4 * _FIRST_RESTART  # given up, the work runs on
    assert (
        LoggedLine(
            level="error",
            message="client: 3 useless restarts, its components failing; not restarted again",
        )
        in logger.lines
    )


def test_a_restart_stops_the_works_feeding_its_owner_s_components_and_those_alone(
    virtual_loop: VirtualLoop,
) -> None:
    search, status, webui = _component("search"), _component("status"), _component("webui")
    unowned = _PacedWork("webui", wait_seconds=10.0)

    _, builds = _supervise_owned(
        virtual_loop,
        build=lambda: [_broken(search), _steady(status)],
        seconds=_FIRST_RESTART + 25.0,
        unowned=lambda recorder: _supervised(unowned, feeds=(webui,)),
        owned_by_another=(webui,),
    )

    turns = [[w.work.turns for w in build if isinstance(w.work, _PacedWork)] for build in builds]
    assert turns == [
        [[1.0, 1.0 + _FLOOR, _FIRST_RESTART], [10.0 * n for n in range(1, 13)]],
        [[_FIRST_RESTART + 1.0], [_FIRST_RESTART + 10.0, _FIRST_RESTART + 20.0]],
    ]
    assert unowned.turns == [10.0 * n for n in range(1, 15)]


def test_a_rebuild_that_raises_records_a_bug_on_each_component_and_is_tried_after_the_floor(
    virtual_loop: VirtualLoop,
) -> None:
    logger, health_logger = FakeLogger(), FakeLogger()
    search, status = _component("search"), _component("status")
    refused = LookupError("login refused")
    between: list[Health | None] = []
    for attempt in range(2):
        at = _FIRST_RESTART + attempt * _FLOOR + 30.0
        virtual_loop.call_at(at, lambda: between.append(search.health_of(BUGS)))

    owner, builds = _supervise_owned(
        virtual_loop,
        build=lambda: [_broken(search), _steady(status)],
        seconds=_FIRST_RESTART + 2 * _FLOOR + 15.0,
        raising=[refused, refused],
        logger=logger,
        health_logger=health_logger,
    )

    assert owner.attempts == [_FIRST_RESTART + n * _FLOOR for n in range(3)]
    assert between == [Health.FAILING, Health.FAILING]
    raised = LoggedLine(level="error", message="restart of client raised", error=refused)
    assert [line for line in logger.lines if line.error is refused] == [raised, raised]
    # Healthy on its ten successes, degraded at its second bug among its last ten.
    assert health_logger.lines[-1] == LoggedLine(
        level="warning", message="status, bugs: healthy to degraded"
    )
    rebuilt = [w.work.turns for w in builds[1] if isinstance(w.work, _PacedWork)]
    assert rebuilt == [[owner.attempts[-1] + 1.0], [owner.attempts[-1] + 10.0]]


def test_the_works_a_raising_rebuild_added_are_stopped_before_the_next_attempt(
    virtual_loop: VirtualLoop,
) -> None:
    search, status = _component("search"), _component("status")

    owner, builds = _supervise_owned(
        virtual_loop,
        build=lambda: [_broken(search), _steady(status)],
        seconds=_FIRST_RESTART + 2 * _FLOOR,
        raising=[LookupError("login refused")],
        raising_after_adding=True,
    )

    assert owner.attempts == [_FIRST_RESTART, _FIRST_RESTART + _FLOOR]
    # The first attempt's works stopped at the second's head, its steady work's last turn before.
    [_, after_raising, _] = builds
    steady = after_raising[1].work
    assert isinstance(steady, _PacedWork)
    assert steady.turns[-1] < owner.attempts[-1]


def test_three_raising_rebuilds_give_the_owner_up_its_works_stopped_the_node_running(
    virtual_loop: VirtualLoop,
) -> None:
    logger = FakeLogger()
    search = _component("search")

    owner, builds = _supervise_owned(
        virtual_loop,
        build=lambda: [_broken(search)],
        seconds=_FIRST_RESTART + 5 * _FLOOR,
        raising=[LookupError("login refused")] * 3,
        logger=logger,
    )

    assert owner.attempts == [_FIRST_RESTART + n * _FLOOR for n in range(3)]
    [[broken]] = builds
    assert isinstance(broken.work, _PacedWork)
    assert broken.work.turns == [1.0, 1.0 + _FLOOR, _FIRST_RESTART]  # stopped for good
    assert logger.lines[-1] == LoggedLine(
        level="error",
        message="client: 3 useless restarts, its components failing; not restarted again",
    )


def test_a_restart_in_flight_is_cancelled_at_the_shutdown(virtual_loop: VirtualLoop) -> None:
    search = _component("search")
    owner, _ = _supervise_owned(
        virtual_loop,
        build=lambda: [_broken(search)],
        seconds=_FIRST_RESTART + 30.0,
        raising=[LookupError("login refused")] * 3,
    )
    assert owner.attempts == [_FIRST_RESTART]
    assert virtual_loop.time() == _FIRST_RESTART + 30.0


def test_an_owner_whose_components_no_work_feeds_is_restarted_all_the_same(
    virtual_loop: VirtualLoop,
) -> None:
    notifier, recorder_s = _component("notifier"), _component("bug recorder")

    owner, _ = _supervise_owned(
        virtual_loop,
        build=list,
        seconds=35.0,
        owned=(notifier,),
        unowned=lambda recorder: _supervised(
            _BugRecorder(recorder=recorder, on=notifier), feeds=(recorder_s,)
        ),
        owned_by_another=(recorder_s,),
    )

    assert owner.attempts == [30.0]


def test_a_work_added_while_none_runs_is_refused() -> None:
    supervisor = _supervisor(run_state=FakeRunStateStore())
    [supervised] = _supervised(_CountedWork())
    with pytest.raises(RuntimeError, match="^counted: added while no work runs$"):
        supervisor.add(supervised)
