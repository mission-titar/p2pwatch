"""The parts built later: the recorder and the supervisor, reached by the parts built before them,
a read before either is set refused by name."""

from datetime import timedelta

import pytest

from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.application.steps.supervisor import SupervisedWork, Supervisor
from p2pwatch.application.steps.webui_liveness import WebuiLiveness
from p2pwatch.composition.parts_built_later import PartNotBuiltYetError, PartsBuiltLater
from p2pwatch.domain.health.health_condition import BUGS, Health
from p2pwatch.domain.health.outcome import UNITS_OF_WORK, Outcome
from p2pwatch.domain.work_components import webui_component
from tests.fakes.adapters.driven.fake_blocking_monotonic_clock import FakeBlockingMonotonicClock
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore

pytestmark = pytest.mark.asyncio


async def test_an_outcome_recorded_before_the_recorder_is_set_is_refused_by_name() -> None:
    with pytest.raises(PartNotBuiltYetError, match="^the health recorder, read before it is set$"):
        await PartsBuiltLater().record(Outcome.success(), on=webui_component(), by=UNITS_OF_WORK)


async def test_a_work_added_before_the_supervisor_is_set_is_refused_by_name() -> None:
    later = PartsBuiltLater()
    with pytest.raises(PartNotBuiltYetError, match="^the supervisor, read before it is set$"):
        later.add_work(_liveness_like())


async def test_an_outcome_recorded_once_the_recorder_is_set_reaches_it() -> None:
    later, webui = PartsBuiltLater(), webui_component()
    later.health_recorder = HealthRecorder(logger=FakeLogger(), subscribers=())
    for _ in range(3):
        await later.record(Outcome.success(), on=webui, by=UNITS_OF_WORK)
    assert webui.health_of(BUGS) is Health.HEALTHY


async def test_a_work_added_once_the_supervisor_is_set_reaches_it() -> None:
    later = PartsBuiltLater()
    later.supervisor = Supervisor(
        run_state_reader=FakeRunStateStore(),
        monotonic_clock=FakeBlockingMonotonicClock(),
        health_recorder=HealthRecorder(logger=FakeLogger(), subscribers=()),
        restart_policy=RestartPolicy(owners={}, logger=FakeLogger()),
        logger=FakeLogger(),
    )
    # The supervisor's own refusal, so the work reached it.
    with pytest.raises(RuntimeError, match="added while no work runs"):
        later.add_work(_liveness_like())


def _liveness_like() -> SupervisedWork:
    return SupervisedWork(
        work=WebuiLiveness(thread_alive=lambda: True, monotonic_clock=FakeBlockingMonotonicClock()),
        time_limit=timedelta(minutes=1),
        feeds=(webui_component(),),
    )
