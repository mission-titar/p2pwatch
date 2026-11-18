"""A subscriber of the node's health built after it: a change passed on before the composition
set it raises, naming it; after, the subscriber takes it."""

import pytest

from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.restart_policy import RestartPolicy, RestartRequest
from p2pwatch.composition.health_subscriber_built_later import (
    HealthSubscriberBuiltLater,
    HealthSubscriberNotSetError,
)
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.work_components import BUGS, status_reading_component
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.composition.fake_restartable_builder import FakeRestartableBuilder

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("subscriber", ["the restart policy", "the alerts"])
async def test_a_change_of_health_passed_on_before_the_subscriber_is_set_raises_naming_it(
    subscriber: str,
) -> None:
    later = HealthSubscriberBuiltLater(subscriber)
    node_health = NodeHealth(logger=FakeLogger(), subscribers=(later,))
    part = status_reading_component(ClientName("amuled"))

    with pytest.raises(
        HealthSubscriberNotSetError, match=f"^{subscriber}, reached before it is set$"
    ):
        for _ in range(3):
            await node_health.record(on=part, rule=BUGS, detected=True)


async def test_once_set_the_subscriber_takes_each_change_of_health() -> None:
    later = HealthSubscriberBuiltLater("the restart policy")
    node_health = NodeHealth(logger=FakeLogger(), subscribers=(later,))
    part = status_reading_component(ClientName("amuled"))
    requests: list[RestartRequest] = []
    client = FakeRestartableBuilder()
    later.set(
        RestartPolicy(
            components_of={client: [part]}, works=(), restart=requests.append, logger=FakeLogger()
        )
    )

    for _ in range(3):
        await node_health.record(on=part, rule=BUGS, detected=True)

    assert [request.builder for request in requests] == [client]
