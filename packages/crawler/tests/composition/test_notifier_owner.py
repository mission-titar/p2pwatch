"""The notifier's owner: the dispatcher reaches the notifier through it, so a restart builds the
notifier anew without rebuilding the dispatcher; the notifier failing on its bugs restarts it."""

import asyncio
from datetime import timedelta

import pytest

from p2pwatch.application.ports.driven.state_owner import StateOwner
from p2pwatch.application.steps.health_event_translator import HealthEventTranslator
from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.composition.notifier_owner import NotifierOwner
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.health.health_condition import BUGS, Health
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.matching.identifiers import TargetId
from p2pwatch.domain.observability import events as ev
from p2pwatch.domain.observability.notifier_outcomes import notifier_components
from tests.contracts.application.ports.driven.state_owner_contract import StateOwnerContract
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier
from tests.fakes.adapters.driven.fake_raising_notifier import FakeRaisingNotifier
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.support.virtual_time import VirtualLoop

_NODE_ID = NodeId("titar-node-1")
_COMPLETED = ev.DownloadCompleted(
    file=FileKey(network=Network.ED2K, native_id="a" * 32),
    filename="Keroro 062.avi",
    target_titles=(ev.TargetTitle(target_id=TargetId("062A"), title="t"),),
    node_id=_NODE_ID,
)


def _dispatcher(owner: NotifierOwner) -> ObservabilityDispatcher:
    """A dispatcher reaching the notifier through ``owner``, as the composition builds it."""
    return ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=FakeNodeMetricStore(),
        current_notifier=owner.notifier,
        notification_timeout_seconds=5.0,
        record_outcome=HealthRecorder(logger=FakeLogger(), subscribers=()).record,
        service_components=notifier_components(owner.notifier().services()),
    )


class TestNotifierOwner(StateOwnerContract):
    @pytest.fixture
    def owner(self) -> NotifierOwner:
        self._built: list[FakeNotifier] = []
        owner = NotifierOwner(build_notifier=self._build)
        self._dispatcher = _dispatcher(owner)
        return owner

    def _build(self) -> FakeNotifier:
        self._built.append(FakeNotifier())
        return self._built[-1]

    def state_of(self, owner: StateOwner) -> object:
        return self._built[-1]

    async def state_relied_on(self, owner: StateOwner) -> object:
        await self._dispatcher.dispatch(_COMPLETED)
        (reached,) = (notifier for notifier in self._built if notifier.calls)
        reached.calls.clear()
        return reached


def test_the_owner_is_named_after_the_notifier() -> None:
    assert str(NotifierOwner(build_notifier=FakeNotifier)) == "notifier"


def test_a_notifier_failing_on_its_bugs_restarts_its_owner_the_sends_then_reaching_the_new_one(
    virtual_loop: VirtualLoop,
) -> None:
    # The composition's cycle: the translator, a subscriber, dispatches through the dispatcher
    # recording on the same recorder, and none of the notifier's transitions is an event.
    raising, rebuilt = FakeRaisingNotifier(KeyError("embeds")), FakeNotifier()
    built = iter((raising, rebuilt))
    owner = NotifierOwner(build_notifier=lambda: next(built))
    components, policy_logger = notifier_components(owner.notifier().services()), FakeLogger()
    [community, _] = components.values()  # each send is the community's
    recorder: HealthRecorder
    dispatcher = ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=FakeNodeMetricStore(),
        current_notifier=owner.notifier,
        notification_timeout_seconds=5.0,
        record_outcome=lambda outcome, *, on, by: recorder.record(outcome, on=on, by=by),
        service_components=components,
    )
    policy = RestartPolicy(owners=dict.fromkeys(components.values(), owner), logger=policy_logger)
    recorder = HealthRecorder(
        logger=FakeLogger(),
        subscribers=(
            HealthEventTranslator(observability_dispatcher=dispatcher, node_id=_NODE_ID).translate,
            policy,
        ),
    )
    clock, run_state = FakeLoopMonotonicClock(virtual_loop), FakeRunStateStore()
    supervisor = Supervisor(
        run_state_reader=run_state,
        monotonic_clock=clock,
        health_recorder=recorder,
        restart_policy=policy,
        logger=FakeLogger(),
    )

    async def three_sends_a_second_apart() -> None:
        for _ in range(3):
            await dispatcher.dispatch(_COMPLETED)
            await clock.sleep(timedelta(seconds=1))

    async def scenario() -> None:
        supervising = asyncio.create_task(supervisor.supervise([], arm_shutdown_bound=lambda: None))
        await three_sends_a_second_apart()
        await three_sends_a_second_apart()
        run_state.set_shutdown_requested()
        await supervising

    virtual_loop.run_until_complete(scenario())
    assert (raising.calls, len(rebuilt.calls)) == (3, 3)
    assert community.health_of(BUGS) is Health.HEALTHY
    assert policy_logger.lines == [
        LoggedLine(
            level="warning", message="notifier fake community, bugs failing: restarting notifier"
        )
    ]
