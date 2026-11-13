"""The webui's liveness: a turn each status period, a fallen webui thread its bug, its bugs
condition failing restarting the thread's owner."""

import pytest

from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.application.steps.supervisor import SupervisedWork, Supervisor
from p2pwatch.application.steps.webui_liveness import WebuiFallen, WebuiLiveness
from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.health_condition import BUGS, Health
from p2pwatch.domain.status_reading import STATUS_PERIOD
from p2pwatch.domain.work_components import webui_component
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.composition.fake_state_owner import FakeStateOwner
from tests.support.virtual_time import VirtualLoop


class _WebuiThread:
    """The webui thread's liveness as the test sets it."""

    def __init__(self, *, alive: bool) -> None:
        self.alive = alive

    def is_alive(self) -> bool:
        return self.alive

    def fall(self) -> None:
        self.alive = False


@pytest.mark.asyncio
async def test_a_turn_over_a_live_webui_thread_succeeds() -> None:
    liveness = WebuiLiveness(
        thread_alive=_WebuiThread(alive=True).is_alive, monotonic_clock=FakeTime().monotonic
    )
    await liveness.run_once()


@pytest.mark.asyncio
async def test_a_turn_over_a_fallen_webui_thread_raises_a_bug() -> None:
    liveness = WebuiLiveness(
        thread_alive=_WebuiThread(alive=False).is_alive, monotonic_clock=FakeTime().monotonic
    )
    with pytest.raises(WebuiFallen) as raised:
        await liveness.run_once()
    assert not isinstance(raised.value, DeclaredFailure)
    assert str(liveness) == "webui liveness"


@pytest.mark.asyncio
async def test_each_turn_waits_a_status_period_the_first_included() -> None:
    fake_time = FakeTime()
    liveness = WebuiLiveness(
        thread_alive=_WebuiThread(alive=True).is_alive, monotonic_clock=fake_time.monotonic
    )
    for _ in range(2):
        await liveness.wait_for_next_turn()
        await liveness.run_once()
    assert fake_time.sleeps == [STATUS_PERIOD, STATUS_PERIOD]


def test_a_fallen_webui_restarts_its_owner_at_its_third_bug_the_rebuilt_thread_healthy(
    virtual_loop: VirtualLoop,
) -> None:
    fallen = _WebuiThread(alive=True)
    webui = webui_component()
    clock = FakeLoopMonotonicClock(virtual_loop)
    supervisor: Supervisor

    def liveness_over(thread: _WebuiThread) -> SupervisedWork:
        return SupervisedWork(
            work=WebuiLiveness(thread_alive=thread.is_alive, monotonic_clock=clock),
            time_limit=STATUS_PERIOD,
            feeds=(webui,),
        )

    owner = FakeStateOwner(
        "webui thread",
        add_works=lambda _: supervisor.add(liveness_over(_WebuiThread(alive=True))),
    )
    policy_logger = FakeLogger()
    policy = RestartPolicy(owners={webui: owner}, logger=policy_logger)
    run_state = FakeRunStateStore()
    # Fallen between its first and second turns, a minute apart: failing at its fourth.
    virtual_loop.call_later(90.0, fallen.fall)
    virtual_loop.call_later(450.0, run_state.set_shutdown_requested)
    supervisor = Supervisor(
        run_state_reader=run_state,
        monotonic_clock=clock,
        health_recorder=HealthRecorder(logger=FakeLogger(), subscribers=(policy,)),
        restart_policy=policy,
        logger=FakeLogger(),
    )
    virtual_loop.run_until_complete(
        supervisor.supervise([liveness_over(fallen)], arm_shutdown_bound=lambda: None)
    )
    assert owner.attempts == [240.0]
    assert webui.health_of(BUGS) is Health.HEALTHY
    assert policy_logger.lines == [
        LoggedLine(level="warning", message="webui, bugs failing: restarting webui thread")
    ]
