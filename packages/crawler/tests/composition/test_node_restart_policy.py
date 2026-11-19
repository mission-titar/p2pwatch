"""The node's restart policy: each object is rebuilt when a bugs rule of one of its parts turns
failing, the other objects left as they are: a part its works are recorded on, the notifier's
work recorded on one per notification service."""

import asyncio
from collections.abc import Coroutine, Sequence
from datetime import timedelta

import pytest

from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.application.ports.driven.restartable_builder import RestartableBuilder
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.notification_outbox import NotificationOutbox
from p2pwatch.application.steps.notification_sender import NotificationSender
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.composition.node_restart_policy import node_restart_policy
from p2pwatch.domain.health.external_dependency import ExternalDependency, HealthTransition
from p2pwatch.domain.identifiers import ClientName, NodeId
from p2pwatch.domain.observability.notification import RelayedLogLine
from p2pwatch.domain.observability.notification_sends import (
    NotificationService,
    local_database_dependency,
    notification_service_dependencies,
)
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.work_dependencies import BUGS, status_reading_dependency, webui_dependency
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_notification_outbox_store import FakeNotificationOutboxStore
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE, FakeNotifier
from tests.fakes.adapters.driven.fake_raising_notifier import FakeRaisingNotifier
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.fakes.composition.fake_restartable_builder import FakeRestartableBuilder

pytestmark = pytest.mark.asyncio

_ONLINE = RelayedLogLine(message="🟢 node online", severity=Severity.INFO, node_id=NodeId("n1"))


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


def _recorded_on(part: ExternalDependency) -> SupervisedWork:
    return SupervisedWork(
        work=_Never(part.name), time_limit=timedelta(minutes=5), dependencies=(part,)
    )


async def _restarts_run() -> None:
    """Lets the supervisor run every restart already asked for."""
    for _ in range(20):
        await asyncio.sleep(0)  # noqa: TID251


class _Node:
    """The aMule client and the webui, each with one work on a part of its own, the notifier with
    the work sending the outbox's notifications through ``notifier``, on a part per service, the
    restart policy and the supervisor wired as the node wires them."""

    def __init__(self, *, notifier: Notifier | None = None) -> None:
        self.status_reading_part = status_reading_dependency(ClientName("amuled"))
        self.webui_part = webui_dependency()
        self.client = FakeRestartableBuilder(
            "client amuled", works_over=lambda _: [_recorded_on(self.status_reading_part)]
        )
        self.webui = FakeRestartableBuilder(
            "webui", works_over=lambda _: [_recorded_on(self.webui_part)]
        )
        self.notifier = FakeRestartableBuilder("notifier", works_over=lambda _: self._sending())
        self.service_parts = notification_service_dependencies(ONE_SERVICE_PER_AUDIENCE)
        outbox_store = FakeNotificationOutboxStore()
        self.outbox = NotificationOutbox(
            writer=outbox_store,
            reader=outbox_store,
            services=ONE_SERVICE_PER_AUDIENCE,
            waker=FakeWaker(),
            logger=FakeLogger(),
        )
        self._sending_notifier = notifier or FakeNotifier()  # a rebuild's sends go to it again
        self._run_state = FakeRunStateStore()
        self.node_health = NodeHealth(logger=FakeLogger(), subscribers=(self._to_policy,))
        self._supervisor = Supervisor(
            run_state_reader=self._run_state,
            monotonic_clock=FakeTime().monotonic,
            node_health=self.node_health,
            logger=FakeLogger(),
        )
        self._policy: RestartPolicy  # built over the first objects, once they are built

    def _sending(self) -> Sequence[SupervisedWork]:
        sender = NotificationSender(
            outbox=self.outbox,
            notifier=self._sending_notifier,
            notification_timeout_seconds=5.0,
            record_check=self.node_health.record,
            service_dependencies=self.service_parts,
            local_database=local_database_dependency(),
            logger=FakeLogger(),
        )
        parts = tuple(self.service_parts.values())
        return [SupervisedWork(work=sender, time_limit=timedelta(minutes=5), dependencies=parts)]

    async def _to_policy(self, transition: HealthTransition) -> None:
        await self._policy(transition)

    def rebuilds(self) -> tuple[int, int, int]:
        """How many times the client, the webui and the notifier were rebuilt."""
        return (self.client.rebuilds(), self.webui.rebuilds(), self.notifier.rebuilds())

    async def supervising(
        self,
        checks: Coroutine[None, None, None],
        *,
        running: Sequence[FakeRestartableBuilder] = (),
    ) -> None:
        """Builds each object, then records ``checks`` while the supervisor runs the works of
        those ``running``, then the restarts they asked for."""
        works_of: dict[RestartableBuilder[SupervisedWork], Sequence[SupervisedWork]] = {
            builder: await self._supervisor.build_first(builder)
            for builder in (self.client, self.webui, self.notifier)
        }
        self._policy = node_restart_policy(works_of, supervisor=self._supervisor)
        works = [supervised for builder in running for supervised in works_of[builder]]
        supervision = asyncio.create_task(
            self._supervisor.supervise(works, arm_shutdown_bound=lambda: None)
        )
        await checks
        await _restarts_run()
        self._run_state.set_shutdown_requested()
        await supervision

    async def three_bugs_on(self, part: ExternalDependency) -> None:
        """Three turns in a row meeting a bug on ``part``, then the rebuild they ask for."""
        for _ in range(3):
            await self.node_health.record(on=part, rule=BUGS, detected=True)

    async def every_notification_sent(self) -> None:
        """Returns once the outbox holds no notification."""
        while self.outbox.oldest() is not None:
            await asyncio.sleep(0)  # noqa: TID251


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
    raising = FakeRaisingNotifier(RuntimeError("an embed apprise cannot build"))
    node = _Node(notifier=raising)  # each rebuild in vain: the notifier still raises
    for _ in range(20):
        node.outbox.leave(_ONLINE, services=[ONE_SERVICE_PER_AUDIENCE[1]])

    await node.supervising(node.every_notification_sent(), running=[node.notifier])

    assert raising.sends == 20
    assert node.rebuilds() == (0, 0, 3)
