"""The webui's thread watch: every minute, whether the webui's thread still runs; a thread that has
ended is a bug of the webui, which the node rebuilds at the third in a row."""

from collections.abc import Sequence
from datetime import timedelta

import pytest

from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.webui_thread_watch import (
    WebuiThreadEndedError,
    WebuiThreadWatch,
)
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.domain.expected_error import ExpectedError
from p2pwatch.domain.health.component import HealthTransition
from p2pwatch.domain.health.health_rule import HealthState
from p2pwatch.domain.work_components import BUGS, webui_component
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.composition.fake_restartable import FakeRestartable
from tests.support.virtual_time import VirtualLoop


class _WebuiThread:
    """The webui's thread, running until the test ends it."""

    def __init__(self) -> None:
        self.alive = True

    def is_alive(self) -> bool:
        return self.alive

    def end(self) -> None:
        self.alive = False


def _watch(thread: _WebuiThread, *, fake_time: FakeTime | None = None) -> WebuiThreadWatch:
    clock = (fake_time or FakeTime()).monotonic
    return WebuiThreadWatch(thread_alive=thread.is_alive, monotonic_clock=clock)


@pytest.mark.asyncio
async def test_a_turn_over_a_running_thread_raises_nothing() -> None:
    await _watch(_WebuiThread()).run_once()


@pytest.mark.asyncio
async def test_a_turn_over_an_ended_thread_raises_a_bug() -> None:
    thread = _WebuiThread()
    watch = _watch(thread)
    thread.end()

    with pytest.raises(WebuiThreadEndedError) as raised:
        await watch.run_once()

    # A bug, never an expected error: the bugs rule counts it, and a failing one rebuilds.
    assert not isinstance(raised.value, ExpectedError)
    assert str(raised.value) == "the webui's thread has ended while the node runs"


@pytest.mark.asyncio
async def test_each_turn_waits_a_minute_the_first_included() -> None:
    fake_time = FakeTime()
    watch = _watch(_WebuiThread(), fake_time=fake_time)

    for _ in range(2):
        await watch.wait_for_next_turn()
        await watch.run_once()

    assert fake_time.sleeps == [timedelta(minutes=1), timedelta(minutes=1)]


@pytest.mark.asyncio
async def test_the_log_names_it_as_its_part_the_webui() -> None:
    assert str(_watch(_WebuiThread())) == "webui"


class _Webui:
    """The webui and its thread watch under the supervisor and the restart policy, as the node
    wires them; each rebuild builds a thread anew, serving if ``rebuilt_threads_serve``."""

    def __init__(self, loop: VirtualLoop, *, rebuilt_threads_serve: bool) -> None:
        self.loop = loop
        self.logger = FakeLogger()
        self.part = webui_component()
        self.first_thread = _WebuiThread()
        self._rebuilt_threads_serve = rebuilt_threads_serve
        self.webui = FakeRestartable("webui", works_over=self._works_over_a_new_thread)
        self._run_state = FakeRunStateStore()
        self._supervisor = Supervisor(
            run_state_reader=self._run_state,
            monotonic_clock=FakeLoopMonotonicClock(loop),
            node_health=NodeHealth(logger=FakeLogger(), subscribers=(self._to_policy,)),
            logger=self.logger,
        )
        self._first_works = self._watch_over(self.first_thread)
        self._policy = RestartPolicy(
            components_of={self.webui: [self.part]},
            works=self._first_works,
            restart=self._supervisor.restart,
            logger=FakeLogger(),
        )

    async def _to_policy(self, transition: HealthTransition) -> None:
        await self._policy(transition)

    def _watch_over(self, thread: _WebuiThread) -> Sequence[SupervisedWork]:
        watch = WebuiThreadWatch(
            thread_alive=thread.is_alive, monotonic_clock=FakeLoopMonotonicClock(self.loop)
        )
        return [
            SupervisedWork(work=watch, time_limit=timedelta(minutes=5), components=(self.part,))
        ]

    def _works_over_a_new_thread(self, _state: object, /) -> Sequence[SupervisedWork]:
        thread = _WebuiThread()
        if not self._rebuilt_threads_serve:
            thread.end()  # its bind failed: the port is held elsewhere
        return self._watch_over(thread)

    def run_for(self, seconds: float) -> None:
        self.loop.call_later(seconds, self._run_state.set_shutdown_requested)
        self.loop.run_until_complete(
            self._supervisor.supervise(self._first_works, arm_shutdown_bound=lambda: None)
        )

    def bug_lines(self) -> int:
        return sum(1 for line in self.logger.lines if line.message == "bug in webui")


def test_a_thread_ended_has_the_webui_rebuilt_at_the_third_watch_after(
    virtual_loop: VirtualLoop,
) -> None:
    webui = _Webui(virtual_loop, rebuilt_threads_serve=True)
    # Ended between the watch's first look, at 60 s, which found it running, and its second.
    virtual_loop.call_later(90.0, webui.first_thread.end)

    webui.run_for(900.0)

    # Its looks at 120, 180 and 240 s met the ended thread; the new thread's watch finds it serving.
    assert webui.webui.rebuilt_at == [240.0]
    assert webui.bug_lines() == 3
    assert webui.part.state(BUGS) is HealthState.HEALTHY


def test_a_webui_whose_rebuilt_threads_never_serve_is_rebuilt_three_times_in_vain_then_no_more(
    virtual_loop: VirtualLoop,
) -> None:
    webui = _Webui(virtual_loop, rebuilt_threads_serve=False)
    webui.first_thread.end()

    webui.run_for(1800.0)

    # Each rebuilt thread's watch meets it ended three times, a minute apart, from a minute on.
    assert webui.webui.rebuilt_at == [180.0, 360.0, 540.0]
    assert webui.part.state(BUGS) is HealthState.FAILING
