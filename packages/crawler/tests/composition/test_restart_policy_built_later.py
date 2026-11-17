"""The restart policy as the node's health reaches it: a change passed on before the composition
set the policy raises, by name; after, the policy takes it."""

import pytest

from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.restart_policy import RestartPolicy, RestartRequest
from p2pwatch.composition.restart_policy_built_later import (
    PartNotBuiltYetError,
    RestartPolicyBuiltLater,
)
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.work_components import BUGS, status_reading_component
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.composition.fake_restartable import FakeRestartable

pytestmark = pytest.mark.asyncio


async def test_a_change_of_health_passed_on_before_the_policy_is_set_raises() -> None:
    later = RestartPolicyBuiltLater()
    node_health = NodeHealth(logger=FakeLogger(), subscribers=(later,))
    part = status_reading_component(ClientName("amuled"))

    with pytest.raises(
        PartNotBuiltYetError, match="^the restart policy, reached before it is set$"
    ):
        for _ in range(3):
            await node_health.record(on=part, rule=BUGS, detected=True)


async def test_once_set_the_policy_takes_each_change_of_health() -> None:
    later = RestartPolicyBuiltLater()
    node_health = NodeHealth(logger=FakeLogger(), subscribers=(later,))
    part = status_reading_component(ClientName("amuled"))
    requests: list[RestartRequest] = []
    client = FakeRestartable()
    later.set(
        RestartPolicy(components_of={client: [part]}, restart=requests.append, logger=FakeLogger())
    )

    for _ in range(3):
        await node_health.record(on=part, rule=BUGS, detected=True)

    assert [request.restartable for request in requests] == [client]
