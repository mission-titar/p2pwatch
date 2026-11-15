from dataclasses import replace

import pytest

from p2pwatch.application.steps.health_alerter import HealthAlerter
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_rule import HealthRule, HealthState
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.observability.notification import Notification, RelayedLogLine
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.status_reading import CHANNEL_NOT_CONNECTED, CLIENT_UNREACHABLE
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


_AMULE = Component(
    name="client amuled", client_name=ClientName("amuled"), rules=(CLIENT_UNREACHABLE,)
)
_KAD = Component(
    name="channel amuled kad",
    client_name=ClientName("amuled"),
    channel=Channel("kad"),
    rules=(CHANNEL_NOT_CONNECTED,),
)


async def _sent(
    *,
    previous: HealthState,
    current: HealthState,
    rule: HealthRule = CLIENT_UNREACHABLE,
    on: Component = _AMULE,
) -> list[Notification]:
    """The notifications sent when the health of ``on`` under ``rule`` changes."""
    notifier = FakeNotifier()
    dispatcher = ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=FakeNodeMetricStore(),
        notifier=notifier,
        notification_timeout_seconds=5.0,
    )
    alerter = HealthAlerter(observability_dispatcher=dispatcher, node_id=_NODE_ID)
    await alerter.send(
        HealthTransition(component=on, rule=rule, previous=previous, current=current)
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
@pytest.mark.parametrize(
    ("previous", "current"),
    [(HealthState.HEALTHY, HealthState.FAILING), (HealthState.FAILING, HealthState.HEALTHY)],
)
async def test_another_rule_failing_or_recovering_sends_nothing(
    *, previous: HealthState, current: HealthState
) -> None:
    other = replace(CLIENT_UNREACHABLE, name="other")
    assert await _sent(previous=previous, current=current, rule=other) == []


_OFF_ITS_NETWORK = RelayedLogLine(
    message="amuled kad: off its network for 5 min", severity=Severity.WARNING, node_id=_NODE_ID
)


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", [HealthState.UNKNOWN, HealthState.HEALTHY])
async def test_a_channel_failing_not_connected_sends_off_its_network_for_5_min(
    previous: HealthState,
) -> None:
    sent = await _sent(
        previous=previous, current=HealthState.FAILING, rule=CHANNEL_NOT_CONNECTED, on=_KAD
    )
    assert sent == [_OFF_ITS_NETWORK]


@pytest.mark.asyncio
async def test_a_channel_connected_again_sends_back_on_its_network() -> None:
    sent = await _sent(
        previous=HealthState.FAILING,
        current=HealthState.HEALTHY,
        rule=CHANNEL_NOT_CONNECTED,
        on=_KAD,
    )
    assert sent == [
        RelayedLogLine(
            message="amuled kad: back on its network", severity=Severity.INFO, node_id=_NODE_ID
        )
    ]


@pytest.mark.asyncio
async def test_a_channel_connected_from_its_first_readings_sends_nothing() -> None:
    sent = await _sent(
        previous=HealthState.UNKNOWN,
        current=HealthState.HEALTHY,
        rule=CHANNEL_NOT_CONNECTED,
        on=_KAD,
    )
    assert sent == []


@pytest.mark.asyncio
async def test_a_channel_s_rule_on_a_component_with_no_channel_raises() -> None:
    with pytest.raises(ValueError, match="client amuled: no channel to name in its alert"):
        await _sent(
            previous=HealthState.HEALTHY, current=HealthState.FAILING, rule=CHANNEL_NOT_CONNECTED
        )
