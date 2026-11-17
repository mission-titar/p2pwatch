"""The node's restart policy: each object is rebuilt when a bugs rule of one of its parts turns
failing, the other objects left as they are: a part its works are recorded on, or one of the
notifier's, one per notification service, which the dispatcher records each send on."""

import asyncio
from collections.abc import Coroutine
from datetime import timedelta

import pytest

from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.composition.node_restart_policy import node_restart_policy
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.identifiers import ClientName, NodeId
from p2pwatch.domain.observability import events as ev
from p2pwatch.domain.observability.notification_sends import (
    NotificationService,
    notification_service_components,
)
from p2pwatch.domain.work_components import BUGS, status_reading_component, webui_component
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE
from tests.fakes.adapters.driven.fake_raising_notifier import FakeRaisingNotifier
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.composition.fake_restartable import FakeRestartable

pytestmark = pytest.mark.asyncio


class _Never(Work):
    """A work whose turns are never taken."""

    def __init__(self, name: str) -> None:
        self._name = name

    def __str__(self) -> str:
        return self._name

    async def wait_for_next_turn(self) -> None:
        """Never awaited."""

    async def run_once(self) -> None:
        """Never awaited."""


def _recorded_on(part: Component) -> SupervisedWork:
    return SupervisedWork(
        work=_Never(part.name), time_limit=timedelta(minutes=5), components=(part,)
    )


async def _restarts_run() -> None:
    """Lets the supervisor run every restart already asked for."""
    for _ in range(20):
        await asyncio.sleep(0)  # noqa: TID251


class _Node:
    """The aMule client and the webui, each with one work on a part of its own, the notifier with
    a part per service and no work, the restart policy and the supervisor wired as the node wires
    them."""

    def __init__(self) -> None:
        self.client = FakeRestartable("client amuled")
        self.webui = FakeRestartable("webui")
        self.notifier = FakeRestartable("notifier")
        self.status_reading_part = status_reading_component(ClientName("amuled"))
        self.webui_part = webui_component()
        self.service_parts = notification_service_components(ONE_SERVICE_PER_AUDIENCE)
        self._run_state = FakeRunStateStore()
        self.node_health = NodeHealth(logger=FakeLogger(), subscribers=(self._to_policy,))
        self._supervisor = Supervisor(
            run_state_reader=self._run_state,
            monotonic_clock=FakeTime().monotonic,
            node_health=self.node_health,
            logger=FakeLogger(),
        )
        self._policy: RestartPolicy = node_restart_policy(
            {
                self.client: [_recorded_on(self.status_reading_part)],
                self.webui: [_recorded_on(self.webui_part)],
            },
            parts_without_works={self.notifier: list(self.service_parts.values())},
            supervisor=self._supervisor,
        )

    async def _to_policy(self, transition: HealthTransition) -> None:
        await self._policy(transition)

    def rebuilds(self) -> tuple[int, int, int]:
        """How many times the client, the webui and the notifier were rebuilt."""
        return (
            len(self.client.rebuilt_at),
            len(self.webui.rebuilt_at),
            len(self.notifier.rebuilt_at),
        )

    async def supervising(self, checks: Coroutine[None, None, None]) -> None:
        """Records ``checks`` while the supervisor runs, then the restarts they asked for."""
        supervision = asyncio.create_task(
            self._supervisor.supervise((), arm_shutdown_bound=lambda: None)
        )
        await checks
        await _restarts_run()
        self._run_state.set_shutdown_requested()
        await supervision

    async def three_bugs_on(self, part: Component) -> None:
        """Three turns in a row meeting a bug on ``part``, then the rebuild they ask for."""
        for _ in range(3):
            await self.node_health.record(on=part, rule=BUGS, detected=True)


async def test_bugs_on_the_webui_s_part_rebuild_the_webui_alone() -> None:
    node = _Node()

    await node.supervising(node.three_bugs_on(node.webui_part))

    assert node.rebuilds() == (0, 1, 0)


async def test_bugs_on_a_part_of_the_client_s_works_rebuild_the_client_alone() -> None:
    node = _Node()

    await node.supervising(node.three_bugs_on(node.status_reading_part))

    assert node.rebuilds() == (1, 0, 0)


@pytest.mark.parametrize("service", ONE_SERVICE_PER_AUDIENCE, ids=str)
async def test_bugs_on_any_notification_service_s_part_rebuild_the_notifier_alone(
    *, service: NotificationService
) -> None:
    node = _Node()

    await node.supervising(node.three_bugs_on(node.service_parts[service]))

    assert node.rebuilds() == (0, 0, 1)


async def test_a_notifier_raising_a_bug_at_every_send_is_rebuilt_three_times_then_never() -> None:
    node = _Node()
    raising = FakeRaisingNotifier(RuntimeError("an embed apprise cannot build"))
    dispatcher = ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=FakeNodeMetricStore(),
        current_notifier=lambda: raising,  # each rebuild in vain: the notifier still raises
        notification_timeout_seconds=5.0,
        record_check=node.node_health.record,
        service_components=node.service_parts,
    )

    async def twenty_sends() -> None:
        for _ in range(20):
            await dispatcher.dispatch(
                ev.CrawlerStarted(download_enabled=True, node_id=NodeId("n1"))
            )
            await _restarts_run()

    await node.supervising(twenty_sends())

    assert raising.sends == 20
    assert node.rebuilds() == (0, 0, 3)
