"""A subscriber of the node's health built after it: a change passed on before the composition
set it raises, naming it; after, the subscriber takes it."""

import pytest

from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.composition.health_subscriber_built_later import (
    HealthSubscriberBuiltLater,
    HealthSubscriberNotSetError,
)
from p2pwatch.domain.health.external_dependency import HealthTransition
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.status_reading import CLIENT_UNREACHABLE, client_dependency
from tests.fakes.adapters.driven.fake_logger import FakeLogger

pytestmark = pytest.mark.asyncio


async def test_a_change_of_health_passed_on_before_the_subscriber_is_set_raises_naming_it() -> None:
    later = HealthSubscriberBuiltLater("the alerts")
    node_health = NodeHealth(logger=FakeLogger(), subscribers=(later,))
    client = client_dependency(ClientName("amuled"))

    with pytest.raises(HealthSubscriberNotSetError, match="^the alerts, reached before it is set$"):
        for _ in range(3):
            await node_health.record(on=client, rule=CLIENT_UNREACHABLE, detected=True)


async def test_once_set_the_subscriber_takes_each_change_of_health() -> None:
    later = HealthSubscriberBuiltLater("the alerts")
    node_health = NodeHealth(logger=FakeLogger(), subscribers=(later,))
    client = client_dependency(ClientName("amuled"))
    taken: list[HealthTransition] = []

    async def take(transition: HealthTransition) -> None:
        taken.append(transition)

    later.set(take)
    for _ in range(3):
        await node_health.record(on=client, rule=CLIENT_UNREACHABLE, detected=True)

    assert [(transition.dependency, transition.rule) for transition in taken] == [
        (client, CLIENT_UNREACHABLE)
    ]
