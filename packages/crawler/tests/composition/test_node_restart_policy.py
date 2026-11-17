"""The node's restart policy: each object is rebuilt when a bugs rule of a part its works are
recorded on turns failing, the other objects left as they are."""

import asyncio
from datetime import timedelta

import pytest

from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.composition.node_restart_policy import node_restart_policy
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.work_components import BUGS, status_reading_component, webui_component
from tests.fakes.adapters.driven.fake_logger import FakeLogger
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


class _Node:
    """The aMule client and the webui, each with one work on a part of its own, the restart
    policy and the supervisor wired as the node wires them."""

    def __init__(self) -> None:
        self.client = FakeRestartable("client amuled")
        self.webui = FakeRestartable("webui")
        self.status_reading_part = status_reading_component(ClientName("amuled"))
        self.webui_part = webui_component()
        self._run_state = FakeRunStateStore()
        self._node_health = NodeHealth(logger=FakeLogger(), subscribers=(self._to_policy,))
        self._supervisor = Supervisor(
            run_state_reader=self._run_state,
            monotonic_clock=FakeTime().monotonic,
            node_health=self._node_health,
            logger=FakeLogger(),
        )
        self._policy: RestartPolicy = node_restart_policy(
            {
                self.client: [_recorded_on(self.status_reading_part)],
                self.webui: [_recorded_on(self.webui_part)],
            },
            supervisor=self._supervisor,
        )

    async def _to_policy(self, transition: HealthTransition) -> None:
        await self._policy(transition)

    async def three_bugs_on(self, part: Component) -> None:
        """Three turns in a row meeting a bug on ``part``, then the rebuild they ask for."""
        supervision = asyncio.create_task(
            self._supervisor.supervise((), arm_shutdown_bound=lambda: None)
        )
        for _ in range(3):
            await self._node_health.record(on=part, rule=BUGS, detected=True)
        while not self.client.rebuilt_at and not self.webui.rebuilt_at:
            await asyncio.sleep(0)  # noqa: TID251
        self._run_state.set_shutdown_requested()
        await supervision


async def test_bugs_on_the_webui_s_part_rebuild_the_webui_alone() -> None:
    node = _Node()

    await node.three_bugs_on(node.webui_part)

    assert (len(node.webui.rebuilt_at), len(node.client.rebuilt_at)) == (1, 0)


async def test_bugs_on_a_part_of_the_client_s_works_rebuild_the_client_alone() -> None:
    node = _Node()

    await node.three_bugs_on(node.status_reading_part)

    assert (len(node.client.rebuilt_at), len(node.webui.rebuilt_at)) == (1, 0)
