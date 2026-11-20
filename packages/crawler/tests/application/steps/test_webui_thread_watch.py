"""The webui's thread watch: every minute, whether the webui's thread still runs; a thread that has
ended is a bug of the webui, which the supervisor rebuilds at the third in a row."""

from collections.abc import Sequence
from datetime import timedelta

import pytest

from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.webui_thread_watch import (
    WebuiThreadEndedError,
    WebuiThreadWatch,
)
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.domain.expected_error import ExpectedError
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.composition.fake_restartable_builder import FakeRestartableBuilder
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

    # A bug, never an expected error: the supervisor counts it, and three in a row rebuild.
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
    """The webui and its thread watch under the supervisor, as the node wires them; each rebuild
    builds a thread anew, serving if ``rebuilt_threads_serve``."""

    def __init__(self, loop: VirtualLoop, *, rebuilt_threads_serve: bool) -> None:
        self.loop = loop
        self.logger = FakeLogger()
        self.first_thread = _WebuiThread()
        self._rebuilt_threads_serve = rebuilt_threads_serve
        self.webui = FakeRestartableBuilder("webui", works_over=self._works_over_a_thread)
        self._run_state = FakeRunStateStore()
        self._supervisor = Supervisor(
            run_state_reader=self._run_state,
            monotonic_clock=FakeLoopMonotonicClock(loop),
            logger=self.logger,
        )
        self._first_works = self._watch_over(self.first_thread)

    def _watch_over(self, thread: _WebuiThread) -> Sequence[SupervisedWork]:
        watch = WebuiThreadWatch(
            thread_alive=thread.is_alive, monotonic_clock=FakeLoopMonotonicClock(self.loop)
        )
        return [SupervisedWork(work=watch, time_limit=timedelta(minutes=5))]

    def _works_over_a_thread(self, _state: object, /) -> Sequence[SupervisedWork]:
        """The first thread's watch at the first build, then a watch over a thread built anew."""
        if not self.webui.built:
            return self._first_works
        thread = _WebuiThread()
        if not self._rebuilt_threads_serve:
            thread.end()  # its bind failed: the port is held elsewhere
        return self._watch_over(thread)

    def run_for(self, seconds: float) -> None:
        self.loop.call_later(seconds, self._run_state.set_shutdown_requested)
        self.loop.run_until_complete(self._run())

    async def _run(self) -> None:
        await self._supervisor.build_first(self.webui)
        await self._supervisor.supervise(arm_shutdown_bound=lambda: None)

    def bug_lines(self) -> int:
        return sum(1 for line in self.logger.lines if line.message == "bug in webui")


def test_a_thread_ended_has_the_webui_rebuilt_a_minute_after_the_third_watch_meeting_it(
    virtual_loop: VirtualLoop,
) -> None:
    webui = _Webui(virtual_loop, rebuilt_threads_serve=True)
    # Ended between the watch's first look, at 60 s, which found it running, and its second.
    virtual_loop.call_later(90.0, webui.first_thread.end)

    webui.run_for(900.0)

    # Its looks at 120, 180 and 240 s met the ended thread; the new thread's watch finds it serving.
    assert webui.webui.built_at == [0.0, 300.0]
    assert webui.bug_lines() == 3


def test_a_webui_whose_rebuilt_threads_never_serve_is_rebuilt_three_times_in_vain_then_no_more(
    virtual_loop: VirtualLoop,
) -> None:
    webui = _Webui(virtual_loop, rebuilt_threads_serve=False)
    webui.first_thread.end()

    webui.run_for(1800.0)

    # Each thread's watch meets it ended three times, a minute apart, from a minute on; each
    # rebuild 1, 2, then 4 min after the third.
    assert webui.webui.built_at == [0.0, 240.0, 540.0, 960.0]
    # Its fourth thread found ended three times too: given up.
    given_up = "webui not restarted again: 3 rebuilds in vain"
    assert LoggedLine(level="error", message=given_up) in webui.logger.lines
