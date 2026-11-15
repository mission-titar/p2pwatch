from dataclasses import replace

import pytest

from p2pwatch.application.steps.health_alerter import HealthAlerter
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_rule import HealthRule, HealthState
from p2pwatch.domain.identifiers import ClientName, NodeId
from p2pwatch.domain.observability.notification import Notification, RelayedLogLine
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.status_reading import CLIENT_UNREACHABLE
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier

_NODE_ID = NodeId("titar-node-1")
_UNREACHABLE = RelayedLogLine(
    message="amuled unreachable for 2 min", severity=Severity.WARNING, node_id=_NODE_ID
)
_REACHABLE_AGAIN = RelayedLogLine(
    message="amuled reachable again", severity=Severity.INFO, node_id=_NODE_ID
)


async def _sent(
    *, previous: HealthState, current: HealthState, rule: HealthRule = CLIENT_UNREACHABLE
) -> list[Notification]:
    """The notifications sent when the aMule client's health under ``rule`` changes."""
    notifier = FakeNotifier()
    dispatcher = ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=FakeNodeMetricStore(),
        notifier=notifier,
        notification_timeout_seconds=5.0,
    )
    amule = Component(name="client amuled", client_name=ClientName("amuled"), rules=(rule,))
    alerter = HealthAlerter(observability_dispatcher=dispatcher, node_id=_NODE_ID)
    await alerter.send(
        HealthTransition(component=amule, rule=rule, previous=previous, current=current)
    )
    return [notification for _, notification in notifier.calls]


@pytest.mark.asyncio
async def test_the_client_failing_at_its_first_readings_sends_unreachable_for_2_min() -> None:
    assert await _sent(previous=HealthState.UNKNOWN, current=HealthState.FAILING) == [_UNREACHABLE]


@pytest.mark.asyncio
async def test_the_client_failing_after_being_healthy_sends_unreachable_for_2_min() -> None:
    assert await _sent(previous=HealthState.HEALTHY, current=HealthState.FAILING) == [_UNREACHABLE]


@pytest.mark.asyncio
async def test_the_client_recovering_sends_reachable_again() -> None:
    assert await _sent(previous=HealthState.FAILING, current=HealthState.HEALTHY) == [
        _REACHABLE_AGAIN
    ]


@pytest.mark.asyncio
async def test_the_client_healthy_from_its_first_readings_sends_nothing() -> None:
    assert await _sent(previous=HealthState.UNKNOWN, current=HealthState.HEALTHY) == []


@pytest.mark.asyncio
async def test_another_rule_failing_sends_nothing() -> None:
    other = replace(CLIENT_UNREACHABLE, name="other")
    assert await _sent(previous=HealthState.HEALTHY, current=HealthState.FAILING, rule=other) == []
