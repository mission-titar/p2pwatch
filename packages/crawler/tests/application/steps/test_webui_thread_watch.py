"""The webui's thread watch: every minute, whether the webui's thread still runs; a thread that has
ended is a bug of the webui."""

from datetime import timedelta

import pytest

from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.restart_policy import RestartPolicy, RestartRequest
from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.webui_thread_watch import (
    WebuiThreadEndedError,
    WebuiThreadWatch,
)
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.domain.expected_error import ExpectedError
from p2pwatch.domain.work_components import webui_component
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
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
async def test_the_log_names_it_the_webui_thread_watch() -> None:
    assert str(_watch(_WebuiThread())) == "webui thread watch"


def test_a_thread_ended_fails_the_webui_at_the_third_watch_after_and_rebuilds_nothing(
    virtual_loop: VirtualLoop,
) -> None:
    thread = _WebuiThread()
    webui = webui_component()
    logger, health_logger = FakeLogger(), FakeLogger()
    requests: list[RestartRequest] = []
    run_state = FakeRunStateStore()
    supervisor = Supervisor(
        run_state_reader=run_state,
        monotonic_clock=FakeLoopMonotonicClock(virtual_loop),
        node_health=NodeHealth(
            logger=health_logger,
            subscribers=(
                RestartPolicy(
                    components_of={FakeRestartable("client amuled"): []},
                    components_restarting_nothing=[webui],
                    works=(),
                    restart=requests.append,
                    logger=logger,
                ),
            ),
        ),
        logger=logger,
    )
    watch = WebuiThreadWatch(
        thread_alive=thread.is_alive, monotonic_clock=FakeLoopMonotonicClock(virtual_loop)
    )
    # Ended between the watch's first look, at 60 s, which found it running, and its second.
    virtual_loop.call_later(90.0, thread.end)
    virtual_loop.call_later(250.0, run_state.set_shutdown_requested)

    virtual_loop.run_until_complete(
        supervisor.supervise(
            [SupervisedWork(work=watch, time_limit=timedelta(minutes=5), components=(webui,))],
            arm_shutdown_bound=lambda: None,
        )
    )

    # Its looks at 120, 180 and 240 s each met the ended thread.
    assert [line.message for line in logger.lines] == ["bug in webui thread watch"] * 3
    assert health_logger.lines == [
        LoggedLine(level="info", message="webui, bugs: unknown to healthy"),
        LoggedLine(level="warning", message="webui, bugs: healthy to failing"),
    ]
    assert requests == []
