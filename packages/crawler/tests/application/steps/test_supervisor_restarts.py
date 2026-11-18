"""The supervisor restarts an object such as the aMule client in a task of its own, as the restart
policy asks: it stops and awaits the works over it, has it rebuilt, then runs the works it hands
back; a rebuild that raises is tried again 60 s later. The tests share one simulated time, on the
virtual-time loop."""

import asyncio
from collections.abc import Iterable, Sequence
from datetime import timedelta
from typing import Protocol

from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.domain.client_errors import ClientAuthError
from p2pwatch.domain.health.external_dependency import ExternalDependency, HealthTransition
from p2pwatch.domain.health.health_rule import HealthState
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.work_dependencies import BUGS
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.composition.fake_restartable import FakeRestartable
from tests.support.virtual_time import VirtualLoop

_DAY = timedelta(days=1)


# The client's works over its ``rebuild``-th rebuild, 0 the client as first built.
class _ClientWorks(Protocol):
    def __call__(self, rebuild: int, /) -> Sequence[SupervisedWork]: ...


class _Reading(Protocol):
    def __call__(self) -> object: ...


class _Turns:
    """Every turn the works over one object took: when, and over which of its rebuilds."""

    def __init__(self) -> None:
        self.taken: list[tuple[int, float]] = []

    def of_rebuild(self, rebuild: int) -> list[float]:
        """When the turns over ``rebuild`` started, 0 the object as first built."""
        return [at for over, at in self.taken if over == rebuild]


class _Searching(Work):
    """Waits a second before each turn, the first included; each turn meets a bug if ``buggy``."""

    def __init__(self, *, rebuild: int, turns: _Turns, buggy: bool) -> None:
        self._rebuild = rebuild
        self._turns = turns
        self._buggy = buggy

    def __str__(self) -> str:
        return "search 'keroro' amuled kad"

    async def wait_for_next_turn(self) -> None:
        await asyncio.sleep(1.0)  # noqa: TID251

    async def run_once(self) -> None:
        self._turns.taken.append((self._rebuild, asyncio.get_running_loop().time()))
        if self._buggy:
            raise KeyError("results")


class _Blocked(Work):
    """A work whose turn never ends on its own; it notes in ``events`` when its turn is cut."""

    def __init__(self, *, events: list[str]) -> None:
        self._events = events

    def __str__(self) -> str:
        return "download tracking amuled"

    async def wait_for_next_turn(self) -> None:
        """Waits for nothing: its turn starts at once."""

    async def run_once(self) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self._events.append("download tracking cut")
            raise


def _part(name: str) -> ExternalDependency:
    return ExternalDependency(name=name, client_name=ClientName("amuled"), rules=(BUGS,))


class _Node:
    """A supervisor over the works of the aMule client and of the webui, each rebuilt as the
    restart policy decides; the client's works are built anew over each of its rebuilds."""

    def __init__(
        self,
        loop: VirtualLoop,
        *,
        client_works: _ClientWorks,
        rebuild_errors: Iterable[Exception] = (),
    ) -> None:
        self.loop = loop
        self.logger = FakeLogger()
        self.webui_turns = _Turns()
        self.webui_part = _part("webui")
        self._client_works = client_works
        self._rebuilds = 0
        self.client = FakeRestartable(works_over=self._works_over, errors=rebuild_errors)
        self.webui = FakeRestartable("webui")
        self._run_state = FakeRunStateStore()
        self.node_health = NodeHealth(logger=FakeLogger(), subscribers=(self._to_policy,))
        self._supervisor = Supervisor(
            run_state_reader=self._run_state,
            monotonic_clock=FakeLoopMonotonicClock(loop),
            node_health=self.node_health,
            logger=self.logger,
        )
        self._first_works = client_works(0)
        self._policy = RestartPolicy(
            dependencies_of={
                self.client: [c for work in self._first_works for c in work.dependencies],
                self.webui: [self.webui_part],
            },
            works=self._first_works,
            restart=self._supervisor.restart,
            logger=FakeLogger(),
        )

    async def _to_policy(self, transition: HealthTransition) -> None:
        await self._policy(transition)

    def _works_over(self, _state: object, /) -> Sequence[SupervisedWork]:
        self._rebuilds += 1
        return self._client_works(self._rebuilds)

    def at(self, *, seconds: float, read: _Reading) -> list[object]:
        """What ``read`` returns at ``seconds``, once the node has run that long."""
        read_then: list[object] = []
        self.loop.call_later(seconds, lambda: read_then.append(read()))
        return read_then

    def run_for(self, seconds: float) -> None:
        self.loop.call_later(seconds, self._run_state.set_shutdown_requested)
        webui_serving = _Searching(rebuild=0, turns=self.webui_turns, buggy=False)
        works = [
            *self._first_works,
            SupervisedWork(work=webui_serving, time_limit=_DAY, dependencies=(self.webui_part,)),
        ]
        self.loop.run_until_complete(
            self._supervisor.supervise(works, arm_shutdown_bound=lambda: None)
        )


def _one_search(
    turns: _Turns, *, part: ExternalDependency, buggy_until: int | None = None
) -> _ClientWorks:
    """One search over each rebuild, on ``part``, meeting a bug at every turn over the rebuilds
    before ``buggy_until``, over all of them if it is ``None``."""

    def works(rebuild: int) -> Sequence[SupervisedWork]:
        buggy = buggy_until is None or rebuild < buggy_until
        search = _Searching(rebuild=rebuild, turns=turns, buggy=buggy)
        return [SupervisedWork(work=search, time_limit=_DAY, dependencies=(part,))]

    return works


def test_a_bugs_rule_failing_with_no_recovery_rebuilds_its_object_three_times_then_never(
    virtual_loop: VirtualLoop,
) -> None:
    turns = _Turns()
    node = _Node(virtual_loop, client_works=_one_search(turns, part=_part("search")))

    node.run_for(1000.0)

    # Each third bug in a row fails the search's part: at 121 s, then 121 s after each rebuild.
    assert node.client.rebuilt_at == [121.0, 242.0, 363.0]
    assert turns.of_rebuild(0) == [1.0, 61.0, 121.0]
    assert turns.of_rebuild(1) == [122.0, 182.0, 242.0]
    # Given up after the fourth failing: its works run on, only their buggy turns failing.
    assert turns.of_rebuild(3)[-1] == 964.0
    assert node.webui.rebuilt_at == []


def test_a_restart_stops_and_awaits_the_works_over_its_object_before_its_rebuild(
    virtual_loop: VirtualLoop,
) -> None:
    events: list[str] = []
    turns = _Turns()
    search, tracking = _part("search"), _part("download tracking")

    def works(rebuild: int) -> Sequence[SupervisedWork]:
        events.append(f"works over rebuild {rebuild} built")
        tracking_work = _Blocked(events=events)
        return [
            *_one_search(turns, part=search, buggy_until=1)(rebuild),
            SupervisedWork(work=tracking_work, time_limit=_DAY, dependencies=(tracking,)),
        ]

    node = _Node(virtual_loop, client_works=works)

    node.run_for(200.0)

    assert events[:3] == [
        "works over rebuild 0 built",
        "download tracking cut",
        "works over rebuild 1 built",
    ]
    assert turns.of_rebuild(0) == [1.0, 61.0, 121.0]
    assert turns.of_rebuild(1)[:2] == [122.0, 123.0]  # on the new works only, every second
    # The webui is another object: its works never stopped.
    assert node.webui_turns.of_rebuild(0) == [float(second) for second in range(1, 200)]


def test_a_rebuild_that_raises_is_tried_again_60_s_later_its_parts_failing_meanwhile(
    virtual_loop: VirtualLoop,
) -> None:
    turns = _Turns()
    search = _part("search")
    errors = [RuntimeError("no session"), RuntimeError("no session again")]
    node = _Node(
        virtual_loop,
        client_works=_one_search(turns, part=search, buggy_until=1),
        rebuild_errors=errors,
    )
    between_attempts = [
        node.at(seconds=seconds, read=lambda: search.state(BUGS)) for seconds in (150, 210)
    ]

    node.run_for(300.0)

    assert node.client.rebuilt_at == [121.0, 181.0, 241.0]
    assert between_attempts == [[HealthState.FAILING], [HealthState.FAILING]]
    assert turns.of_rebuild(1)[:3] == [242.0, 243.0, 244.0]
    rebuild_lines = [line for line in node.logger.lines if "client amuled" in line.message]
    assert rebuild_lines == [
        LoggedLine(level="error", message="bug in the rebuild of client amuled", error=errors[0]),
        LoggedLine(level="error", message="bug in the rebuild of client amuled", error=errors[1]),
        LoggedLine(level="info", message="client amuled rebuilt"),
    ]


def test_a_rebuild_that_raises_records_a_bug_on_each_part_of_its_object(
    virtual_loop: VirtualLoop,
) -> None:
    search, tracking = _part("search"), _part("download tracking")

    def works(rebuild: int) -> Sequence[SupervisedWork]:
        tracking_work = _Searching(rebuild=rebuild, turns=_Turns(), buggy=False)
        return [
            *_one_search(_Turns(), part=search)(rebuild),
            SupervisedWork(work=tracking_work, time_limit=_DAY, dependencies=(tracking,)),
        ]

    errors = [RuntimeError("no session")] * 3
    node = _Node(virtual_loop, client_works=works, rebuild_errors=errors)
    tracking_bugs = [
        node.at(seconds=seconds, read=lambda: tracking.state(BUGS)) for seconds in (120, 210, 300)
    ]

    node.run_for(400.0)

    # Its own turns worked; each of the three raises at 121, 181 and 241 s is a bug of it too.
    assert node.client.rebuilt_at == [121.0, 181.0, 241.0]
    assert tracking_bugs == [[HealthState.HEALTHY], [HealthState.HEALTHY], [HealthState.FAILING]]


def test_three_rebuilds_that_raise_give_it_up_its_works_stopped_the_node_running(
    virtual_loop: VirtualLoop,
) -> None:
    turns = _Turns()
    errors = [RuntimeError("no session")] * 3
    node = _Node(
        virtual_loop, client_works=_one_search(turns, part=_part("search")), rebuild_errors=errors
    )

    node.run_for(1000.0)

    assert node.client.rebuilt_at == [121.0, 181.0, 241.0]
    assert turns.of_rebuild(0) == [1.0, 61.0, 121.0]
    assert turns.taken == [(0, 1.0), (0, 61.0), (0, 121.0)]
    assert node.webui_turns.of_rebuild(0)[-1] == 999.0


def test_a_rebuild_refused_by_amule_is_logged_in_one_line_and_tried_again(
    virtual_loop: VirtualLoop,
) -> None:
    turns = _Turns()
    refused = ClientAuthError("amuleapi refused the admin password")
    node = _Node(
        virtual_loop,
        client_works=_one_search(turns, part=_part("search"), buggy_until=1),
        rebuild_errors=[refused],
    )

    node.run_for(200.0)

    assert node.client.rebuilt_at == [121.0, 181.0]
    rebuild_lines = [line for line in node.logger.lines if "client amuled" in line.message]
    assert rebuild_lines == [
        LoggedLine(
            level="warning",
            message="rebuild of client amuled: amuleapi refused the admin password",
        ),
        LoggedLine(level="info", message="client amuled rebuilt"),
    ]


def test_a_shutdown_while_a_rebuild_waits_to_be_tried_again_ends_the_supervision(
    virtual_loop: VirtualLoop,
) -> None:
    node = _Node(
        virtual_loop,
        client_works=_one_search(_Turns(), part=_part("search")),
        rebuild_errors=[RuntimeError("no session")] * 3,
    )

    node.run_for(150.0)

    assert node.client.rebuilt_at == [121.0]
