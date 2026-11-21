"""The supervisor judges each work of an object, such as the aMule client's searches, on its own
turns, kept across a rebuild, and rebuilds the object in a task of its own once 3 turns in a row of
one work met a bug: it stops and awaits its works, then, after 1, 2, then 4 min, closes it, has its
builder build another and runs that one's works. Its third rebuild in vain, one that raised
included, leaves it unrepaired, and once a function, such as the crawl, is wholly lost, the
supervision ends with a ``CrawlerRestartError``; the count resets once every work that turned
failing is healthy again, and the shutdown closes the latest of each. The tests share
one simulated time, on the virtual-time loop."""

import asyncio
from collections.abc import Iterable, Sequence
from datetime import timedelta
from typing import Protocol

import pytest

from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.notification_outbox import NotificationOutbox
from p2pwatch.application.steps.notification_sender import NotificationSender
from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.domain.client_errors import ClientAuthError
from p2pwatch.domain.crawler_function import CrawlerFunction
from p2pwatch.domain.crawler_restart_error import CrawlerRestartError
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.notification import RelayedLogLine
from p2pwatch.domain.observability.notification_sends import (
    local_database_dependency,
    notification_service_dependencies,
)
from p2pwatch.domain.observability.severity import Severity
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_notification_outbox_store import FakeNotificationOutboxStore
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE
from tests.fakes.adapters.driven.fake_raising_notifier import FakeRaisingNotifier
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.fakes.composition.fake_restartable_builder import FakeRestartableBuilder
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes
from tests.support.virtual_time import VirtualLoop

_DAY = timedelta(days=1)
_CRAWL_LOST = "the crawl lost after 3 rebuilds"
_ONLINE = RelayedLogLine(message="🟢 node online", severity=Severity.INFO, node_id=NodeId("n1"))


# The client's works over its ``build``-th build, 0 the client as first built.
class _ClientWorks(Protocol):
    def __call__(self, build: int, /) -> Sequence[SupervisedWork]: ...


# Whether the ``turn``-th turn, 0 the first, of a work over the ``build``-th build meets a bug.
class _Bugs(Protocol):
    def __call__(self, *, build: int, turn: int) -> bool: ...


def _always(*, build: int, turn: int) -> bool:
    return True


def _never(*, build: int, turn: int) -> bool:
    return False


def _first_build_buggy(*, build: int, turn: int) -> bool:
    return build == 0


class _Turns:
    """Every turn the works over one object took: when, and over which of its builds."""

    def __init__(self) -> None:
        self.taken: list[tuple[int, float]] = []

    def of_build(self, build: int) -> list[float]:
        """When the turns over ``build`` started, 0 the object as first built."""
        return [at for over, at in self.taken if over == build]


class _Searching(Work):
    """Waits a second before each turn, the first included; each turn meets a bug as ``bugs``
    says."""

    def __init__(
        self,
        *,
        build: int,
        turns: _Turns,
        bugs: _Bugs,
        name: str = "search 'keroro' amuled kad",
    ) -> None:
        self._build = build
        self._turns = turns
        self._bugs = bugs
        self._name = name
        self._taken = 0

    def __str__(self) -> str:
        return self._name

    async def wait_for_next_turn(self) -> None:
        await asyncio.sleep(1.0)  # noqa: TID251

    async def run_once(self) -> None:
        self._turns.taken.append((self._build, asyncio.get_running_loop().time()))
        turn, self._taken = self._taken, self._taken + 1
        if self._bugs(build=self._build, turn=turn):
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
            self._events.append(f"download tracking cut at {asyncio.get_running_loop().time()}")
            raise


class _Node:
    """A supervisor over the works of the aMule client and of the webui, each object rebuilt as
    the supervisor decides; the client's works are built anew over each of its builds."""

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
        self._client_works = client_works
        self._builds = 0
        self.client = FakeRestartableBuilder(
            works_over=self._works_over, rebuild_errors=rebuild_errors
        )
        self.webui = FakeRestartableBuilder("webui", works_over=self._webui_serving)
        self._run_state = FakeRunStateStore()
        # The error its supervision ended with, and when it ended.
        self.restart: CrawlerRestartError | None = None
        self.stopped_at: float | None = None
        self._supervisor = Supervisor(
            run_state_reader=self._run_state,
            monotonic_clock=FakeLoopMonotonicClock(loop),
            logger=self.logger,
        )

    def _works_over(self, _state: object, /) -> Sequence[SupervisedWork]:
        build, self._builds = self._builds, self._builds + 1
        return self._client_works(build)

    def _webui_serving(self, _state: object, /) -> Sequence[SupervisedWork]:
        serving = _Searching(build=0, turns=self.webui_turns, bugs=_never)
        return [SupervisedWork(work=serving, time_limit=_DAY, function=CrawlerFunction.WEBUI)]

    def run_for(self, seconds: float) -> None:
        """Builds each object, runs the node ``seconds`` at most, a function lost ending
        it earlier, then closes what the supervisor holds, as the shutdown does."""
        self.loop.call_later(seconds, self._run_state.set_shutdown_requested)
        self.loop.run_until_complete(self._run())

    async def _run(self) -> None:
        await self._supervisor.build_first(self.client)
        await self._supervisor.build_first(self.webui)
        try:
            await self._supervisor.supervise(arm_shutdown_bound=lambda: None)
        except CrawlerRestartError as restart:
            self.restart = restart
        self.stopped_at = self.loop.time()
        await self._supervisor.close()

    def ended(self) -> tuple[str | None, float | None]:
        """The error its supervision ended with, if any, and when it ended."""
        return (None if self.restart is None else str(self.restart)), self.stopped_at

    def client_lines(self) -> list[LoggedLine]:
        """The lines that name the client: each rebuild decided, and how it ended."""
        return [line for line in self.logger.lines if "client amuled" in line.message]


def _one_search(turns: _Turns, *, bugs: _Bugs = _always) -> _ClientWorks:
    """One search over each build, meeting a bug at each turn ``bugs`` names."""

    def works(build: int) -> Sequence[SupervisedWork]:
        search = _Searching(build=build, turns=turns, bugs=bugs)
        return [SupervisedWork(work=search, time_limit=_DAY, function=CrawlerFunction.CRAWL)]

    return works


def test_bugs_failing_rebuild_their_object_after_1_then_2_then_4_min_then_end_the_supervision(
    virtual_loop: VirtualLoop,
) -> None:
    turns = _Turns()
    node = _Node(virtual_loop, client_works=_one_search(turns))

    node.run_for(1000.0)

    # Each third bug in a row turns its bugs failing, at 121, 302 and 543 s: rebuilt 60, 120,
    # then 240 s later. The webui's turns, every second and healthy, are another object's.
    assert node.client.built_at == [0.0, 181.0, 422.0, 783.0]
    assert turns.of_build(0) == [1.0, 61.0, 121.0]
    assert turns.of_build(1) == [182.0, 242.0, 302.0]
    # Its third rebuild in vain, at 904 s, leaves its one search failing: the crawl is lost.
    assert turns.of_build(3) == [784.0, 844.0, 904.0]
    assert node.ended() == (_CRAWL_LOST, 904.0)
    assert node.webui.rebuilds() == 0


def test_each_rebuild_names_its_object_and_how_many_came_before_in_vain(
    virtual_loop: VirtualLoop,
) -> None:
    node = _Node(virtual_loop, client_works=_one_search(_Turns()))

    node.run_for(1000.0)

    restarting, again = "restarting client amuled", "restarting client amuled again"
    assert node.client_lines() == [
        LoggedLine(level="warning", message=f"{restarting}: bugs in its works"),
        LoggedLine(level="info", message="client amuled rebuilt"),
        LoggedLine(level="warning", message=f"{again}, 1 of 3 rebuilds in vain: bugs in its works"),
        LoggedLine(level="info", message="client amuled rebuilt"),
        LoggedLine(level="warning", message=f"{again}, 2 of 3 rebuilds in vain: bugs in its works"),
        LoggedLine(level="info", message="client amuled rebuilt"),
    ]


def _works(*works: tuple[str, _Bugs, CrawlerFunction | None]) -> _ClientWorks:
    """Each of ``works``, its name, the turns meeting a bug and its function, over each build."""

    def over(build: int) -> Sequence[SupervisedWork]:
        return [
            SupervisedWork(
                work=_Searching(build=build, turns=_Turns(), bugs=bugs, name=name),
                time_limit=_DAY,
                function=function,
            )
            for name, bugs, function in works
        ]

    return over


def _searches(*bugs: _Bugs) -> _ClientWorks:
    """One search per ``bugs``, each on a keyword of its own."""
    return _works(
        *[(f"search '{n}' kad", each, CrawlerFunction.CRAWL) for n, each in enumerate(bugs)]
    )


def test_a_bug_at_every_turn_of_one_of_three_searches_rebuilds_their_object_3_times_then_no_more(
    virtual_loop: VirtualLoop,
) -> None:
    node = _Node(virtual_loop, client_works=_searches(_always, _never, _never))

    node.run_for(1500.0)

    # The healthy turns of the two others, every second, hide none of its bugs; its third rebuild
    # in vain, at 904 s, leaves the client unrepaired, its works running on, the crawl not lost.
    assert node.client.built_at == [0.0, 181.0, 422.0, 783.0]
    assert node.ended() == (None, 1500.0)
    bug_lines = [line for line in node.logger.lines if line.message.startswith("bug in ")]
    assert len(bug_lines) == 21  # its 12th turn over the fourth build at 1444 s
    assert all(isinstance(line.error, KeyError) for line in bug_lines)


@pytest.mark.parametrize(
    ("failing", "healthy", "lost"),
    [
        (CrawlerFunction.CRAWL, CrawlerFunction.DOWNLOADS, _CRAWL_LOST),
        (CrawlerFunction.DOWNLOADS, CrawlerFunction.CRAWL, "the downloads lost after 3 rebuilds"),
    ],
    ids=["the crawl", "the downloads"],
)
def test_every_work_of_a_function_failing_after_three_rebuilds_ends_the_supervision_naming_it(
    virtual_loop: VirtualLoop, *, failing: CrawlerFunction, healthy: CrawlerFunction, lost: str
) -> None:
    works = _works(
        ("status reading amuled", _never, None),
        ("failing 1", _always, failing),
        ("failing 2", _always, failing),
        ("healthy", _never, healthy),
    )
    node = _Node(virtual_loop, client_works=works)

    node.run_for(1500.0)

    # The status reading and a work of another function healthy: the client, unrepaired at its
    # third rebuild in vain, has lost that function alone.
    assert node.ended() == (lost, 904.0)


def test_a_search_healthy_keeps_the_crawl_whatever_the_status_reading_meets(
    virtual_loop: VirtualLoop,
) -> None:
    works = _works(
        ("status reading amuled", _always, None),
        ("search 1", _always, CrawlerFunction.CRAWL),
        ("search 2", _never, CrawlerFunction.CRAWL),
    )
    node = _Node(virtual_loop, client_works=works)

    node.run_for(1500.0)

    assert node.client.built_at == [0.0, 181.0, 422.0, 783.0]
    assert node.ended() == (None, 1500.0)


def test_two_bugs_a_healthy_turn_then_three_bugs_after_a_rebuild_count_it_in_vain(
    virtual_loop: VirtualLoop,
) -> None:
    def bugs(*, build: int, turn: int) -> bool:
        return (build, turn) != (1, 2)

    node = _Node(virtual_loop, client_works=_one_search(_Turns(), bugs=bugs))

    node.run_for(600.0)

    # Still failing at its healthy turn, at 302 s: its third bug in a row since, at 423 s, has
    # its next rebuild wait 2 min.
    assert node.client.built_at == [0.0, 181.0, 543.0]


def test_a_work_healthy_again_resets_no_count_while_another_is_still_failing(
    virtual_loop: VirtualLoop,
) -> None:
    node = _Node(virtual_loop, client_works=_searches(_first_build_buggy, _always))

    node.run_for(450.0)

    # Both failing at 121 s; the first healthy again at 190 s, the second failing on: its third
    # bug since the rebuild, at 302 s, has the next wait 2 min.
    assert node.client.built_at == [0.0, 181.0, 422.0]


def test_after_three_rebuilds_in_vain_its_work_healthy_again_has_the_next_bugs_rebuild_it(
    virtual_loop: VirtualLoop,
) -> None:
    def bugs(*, build: int, turn: int) -> bool:
        return build < 3 or not 5 <= turn < 15

    # The status reading serves no function: none is lost when it fails.
    node = _Node(virtual_loop, client_works=_works(("status reading amuled", bugs, None)))

    node.run_for(1300.0)

    # Unrepaired at 904 s, healthy again at 1092 s, under 2 bugs in its last 10 turns: failing
    # again at 1214 s, its count back at zero, it is rebuilt a minute later.
    assert node.client.built_at == [0.0, 181.0, 422.0, 783.0, 1274.0]


def test_after_two_rebuilds_in_vain_ten_healthy_turns_then_bugs_rebuild_it_1_min_later(
    virtual_loop: VirtualLoop,
) -> None:
    def bugs(*, build: int, turn: int) -> bool:
        return build != 3 or turn >= 10

    node = _Node(virtual_loop, client_works=_one_search(_Turns(), bugs=bugs))

    node.run_for(1700.0)

    # Its fourth build healthy from 786 s, failing at 914 s and rebuilt a minute later, its count
    # back at zero: the next two 2, then 4 min after their bugs fail, at 1095 and 1336 s.
    assert node.client.built_at == [0.0, 181.0, 422.0, 783.0, 974.0, 1215.0, 1576.0]


def test_a_rebuild_stops_and_awaits_the_works_over_its_object_a_minute_before_its_rebuild(
    virtual_loop: VirtualLoop,
) -> None:
    events: list[str] = []
    turns = _Turns()

    def works(build: int) -> Sequence[SupervisedWork]:
        events.append(f"works over build {build} built")
        return [
            *_one_search(turns, bugs=_first_build_buggy)(build),
            SupervisedWork(work=_Blocked(events=events), time_limit=_DAY, function=None),
        ]

    node = _Node(virtual_loop, client_works=works)

    node.run_for(200.0)

    # Cut once its bugs turned failing, then none of its works turning until its rebuild.
    assert events[:3] == [
        "works over build 0 built",
        "download tracking cut at 121.0",
        "works over build 1 built",
    ]
    assert node.client.built_at == [0.0, 181.0]
    assert turns.of_build(0) == [1.0, 61.0, 121.0]
    assert turns.of_build(1)[:2] == [182.0, 183.0]  # on the new works only, every second
    # The webui is another object: its works never stopped.
    assert node.webui_turns.of_build(0) == [float(second) for second in range(1, 200)]


def test_a_rebuild_closes_the_object_before_its_builder_builds_the_next(
    virtual_loop: VirtualLoop,
) -> None:
    closes_at_each_build: list[list[int]] = []
    search = _one_search(_Turns(), bugs=_first_build_buggy)
    node: _Node

    def works(build: int) -> Sequence[SupervisedWork]:
        closes_at_each_build.append([restartable.closes for restartable in node.client.built])
        return search(build)

    node = _Node(virtual_loop, client_works=works)

    node.run_for(200.0)

    # Nothing built before the first; the first closed once before the second was built.
    assert closes_at_each_build == [[], [1]]


def test_the_shutdown_closes_the_object_each_builder_built_latest(
    virtual_loop: VirtualLoop,
) -> None:
    node = _Node(virtual_loop, client_works=_one_search(_Turns(), bugs=_first_build_buggy))

    node.run_for(200.0)

    # The first client closed by its rebuild, the second and the webui by the shutdown.
    closes = [restartable.closes for restartable in [*node.client.built, *node.webui.built]]
    assert closes == [1, 1, 1]


def test_a_rebuild_that_raises_is_tried_again_2_then_4_min_later(virtual_loop: VirtualLoop) -> None:
    turns = _Turns()
    errors = [RuntimeError("no session"), RuntimeError("no session again")]
    node = _Node(
        virtual_loop,
        client_works=_one_search(turns, bugs=_first_build_buggy),
        rebuild_errors=errors,
    )

    node.run_for(600.0)

    # Its bugs failing at 121 s: rebuilt a minute later, then each one that raised in vain.
    assert node.client.built_at == [0.0, 181.0, 301.0, 541.0]
    assert turns.of_build(1)[:3] == [542.0, 543.0, 544.0]
    assert node.client_lines()[1:] == [
        LoggedLine(level="error", message="bug in the rebuild of client amuled", error=errors[0]),
        LoggedLine(level="error", message="bug in the rebuild of client amuled", error=errors[1]),
        LoggedLine(level="info", message="client amuled rebuilt"),
    ]


def test_rebuilds_that_raised_and_bugs_failing_again_after_one_share_one_count(
    virtual_loop: VirtualLoop,
) -> None:
    turns = _Turns()
    node = _Node(
        virtual_loop,
        client_works=_one_search(turns),
        rebuild_errors=[RuntimeError("no session")] * 2,
    )

    node.run_for(800.0)

    # Two that raised, then the one that worked failing again at 662 s: its third in vain.
    assert node.client.built_at == [0.0, 181.0, 301.0, 541.0]
    assert turns.of_build(1)[-1] == 662.0
    assert node.ended() == (_CRAWL_LOST, 662.0)


def test_three_rebuilds_that_raise_end_the_supervision_once_the_third_has_raised(
    virtual_loop: VirtualLoop,
) -> None:
    turns = _Turns()
    errors = [RuntimeError("no session")] * 3
    node = _Node(virtual_loop, client_works=_one_search(turns), rebuild_errors=errors)

    node.run_for(1000.0)

    assert node.client.built_at == [0.0, 181.0, 301.0, 541.0]
    assert turns.taken == [(0, 1.0), (0, 61.0), (0, 121.0)]
    assert node.ended() == (_CRAWL_LOST, 541.0)


def test_a_rebuild_refused_by_amule_is_logged_in_one_line_and_tried_again(
    virtual_loop: VirtualLoop,
) -> None:
    refused = ClientAuthError("amuleapi refused the admin password")
    node = _Node(
        virtual_loop,
        client_works=_one_search(_Turns(), bugs=_first_build_buggy),
        rebuild_errors=[refused],
    )

    node.run_for(400.0)

    assert node.client.built_at == [0.0, 181.0, 301.0]
    assert node.client_lines()[1:] == [
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
        client_works=_one_search(_Turns()),
        rebuild_errors=[RuntimeError("no session")] * 3,
    )

    node.run_for(250.0)

    assert node.client.built_at == [0.0, 181.0]


def test_a_notifier_raising_a_bug_at_every_send_is_rebuilt_after_1_2_then_4_min_then_ends_it(
    virtual_loop: VirtualLoop,
) -> None:
    raising = FakeRaisingNotifier(RuntimeError("an embed apprise cannot build"))
    store = FakeNotificationOutboxStore()
    outbox = NotificationOutbox(
        writer=store,
        reader=store,
        services=ONE_SERVICE_PER_AUDIENCE,
        waker=FakeWaker(),
        logger=FakeLogger(),
    )
    for _ in range(20):
        outbox.leave(_ONLINE, services=[ONE_SERVICE_PER_AUDIENCE[1]])

    def sending(_state: object, /) -> Sequence[SupervisedWork]:
        sender = NotificationSender(
            outbox=outbox,
            notifier=raising,  # each rebuild in vain: the notifier still raises
            notification_timeout_seconds=5.0,
            record_check=NodeHealth(
                logger=FakeLogger(), observability_dispatcher=ObservabilityOverFakes().dispatcher
            ).record,
            service_dependencies=notification_service_dependencies(ONE_SERVICE_PER_AUDIENCE),
            local_database=local_database_dependency(node_id=NodeId("n1")),
            logger=FakeLogger(),
        )
        return [
            SupervisedWork(
                work=sender, time_limit=timedelta(minutes=5), function=CrawlerFunction.NOTIFICATIONS
            )
        ]

    notifier = FakeRestartableBuilder("notifier", works_over=sending)
    run_state = FakeRunStateStore()
    virtual_loop.call_later(1500.0, run_state.set_shutdown_requested)
    supervisor = Supervisor(
        run_state_reader=run_state,
        monotonic_clock=FakeLoopMonotonicClock(virtual_loop),
        logger=FakeLogger(),
    )

    async def supervise() -> None:
        await supervisor.build_first(notifier)
        await supervisor.supervise(arm_shutdown_bound=lambda: None)

    with pytest.raises(CrawlerRestartError, match="^the notifications lost after 3 rebuilds$"):
        virtual_loop.run_until_complete(supervise())

    # Its sends meet a bug at once, then each a minute after: failing at 120, 300, 540, then 900 s.
    assert notifier.built_at == [0.0, 180.0, 420.0, 780.0]
    # A send that met a bug removes its entry: 12 of the 20 tried once, the others kept.
    assert (raising.sends, len(store.read_pending_notifications())) == (12, 8)


def _supervisor() -> Supervisor:
    return Supervisor(
        run_state_reader=FakeRunStateStore(),
        monotonic_clock=FakeTime().monotonic,
        logger=FakeLogger(),
    )


@pytest.mark.asyncio
async def test_build_first_hands_back_the_works_of_the_object_its_builder_built() -> None:
    search = _one_search(_Turns())
    builder = FakeRestartableBuilder(works_over=lambda _state: search(0))

    works = await _supervisor().build_first(builder)

    assert works == builder.built[0].works()


@pytest.mark.asyncio
async def test_its_close_closes_the_latest_built_first_each_one_even_when_another_raises() -> None:
    closed: list[str] = []
    supervisor = _supervisor()
    refused = RuntimeError("the webui's thread would not join")
    for builder in [
        FakeRestartableBuilder("notifier", closed=closed),
        FakeRestartableBuilder("webui", closed=closed, close_error=refused),
        FakeRestartableBuilder("client amuled", closed=closed),
    ]:
        await supervisor.build_first(builder)

    with pytest.raises(RuntimeError) as raised:
        await supervisor.close()

    assert closed == ["client amuled", "webui", "notifier"]
    assert raised.value is refused
