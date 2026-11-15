from dataclasses import replace

import pytest

from p2pwatch.application.steps.health_alerter import HealthAlerter
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.download.disk_space import DISK_SPACE_LOW, download_tracking_component
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_rule import HealthRule, HealthState
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.observability.notification import Notification, RelayedLogLine
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.status_reading import (
    CHANNEL_NOT_CONNECTABLE,
    CHANNEL_NOT_CONNECTED,
    CLIENT_UNREACHABLE,
    channel_component,
    client_component,
)
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


_AMULE = client_component(ClientName("amuled"))
_KAD = channel_component(client_name=ClientName("amuled"), channel=Channel("kad"))
_DOWNLOAD_TRACKING = download_tracking_component(ClientName("amuled"))
_TEN_GIB = 10 * 2**30


async def _sent(
    *,
    previous: HealthState,
    current: HealthState,
    rule: HealthRule = CLIENT_UNREACHABLE,
    on: Component = _AMULE,
    min_free_bytes: int | None = _TEN_GIB,
) -> list[Notification]:
    """The notifications sent when the health of ``on`` under ``rule`` changes."""
    notifier = FakeNotifier()
    dispatcher = ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=FakeNodeMetricStore(),
        notifier=notifier,
        notification_timeout_seconds=5.0,
    )
    alerter = HealthAlerter(
        observability_dispatcher=dispatcher, node_id=_NODE_ID, min_free_bytes=min_free_bytes
    )
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


_CHANNEL_ALERTS = pytest.mark.parametrize(
    ("rule", "alert", "end"),
    [
        (CHANNEL_NOT_CONNECTED, "off its network for 5 min", "back on its network"),
        (CHANNEL_NOT_CONNECTABLE, "not connectable for 5 min", "connectable again"),
    ],
    ids=["not connected", "not connectable"],
)


@pytest.mark.asyncio
@_CHANNEL_ALERTS
@pytest.mark.parametrize("previous", [HealthState.UNKNOWN, HealthState.HEALTHY])
async def test_a_channel_failing_sends_its_alert_for_5_min(
    *, rule: HealthRule, alert: str, end: str, previous: HealthState
) -> None:
    sent = await _sent(previous=previous, current=HealthState.FAILING, rule=rule, on=_KAD)
    assert sent == [
        RelayedLogLine(message=f"amuled kad: {alert}", severity=Severity.WARNING, node_id=_NODE_ID)
    ]


@pytest.mark.asyncio
@_CHANNEL_ALERTS
async def test_a_channel_healthy_again_sends_its_alert_s_end(
    *, rule: HealthRule, alert: str, end: str
) -> None:
    sent = await _sent(
        previous=HealthState.FAILING, current=HealthState.HEALTHY, rule=rule, on=_KAD
    )
    assert sent == [
        RelayedLogLine(message=f"amuled kad: {end}", severity=Severity.INFO, node_id=_NODE_ID)
    ]


@pytest.mark.asyncio
@_CHANNEL_ALERTS
async def test_a_channel_healthy_from_its_first_readings_sends_nothing(
    *, rule: HealthRule, alert: str, end: str
) -> None:
    sent = await _sent(
        previous=HealthState.UNKNOWN, current=HealthState.HEALTHY, rule=rule, on=_KAD
    )
    assert sent == []


@pytest.mark.asyncio
async def test_a_channel_s_rule_on_a_component_with_no_channel_raises() -> None:
    with pytest.raises(ValueError, match="client amuled: no channel to name in its alert"):
        await _sent(
            previous=HealthState.HEALTHY, current=HealthState.FAILING, rule=CHANNEL_NOT_CONNECTED
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", [HealthState.UNKNOWN, HealthState.HEALTHY])
async def test_the_disk_failing_sends_disk_low_under_its_floor(previous: HealthState) -> None:
    sent = await _sent(
        previous=previous, current=HealthState.FAILING, rule=DISK_SPACE_LOW, on=_DOWNLOAD_TRACKING
    )
    assert sent == [
        RelayedLogLine(
            message="download disk low: under the 10.0 GiB floor (no new download)",
            severity=Severity.WARNING,
            node_id=_NODE_ID,
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", [HealthState.UNKNOWN, HealthState.FAILING])
async def test_the_disk_healthy_sends_nothing_since_its_alert_has_no_end(
    previous: HealthState,
) -> None:
    sent = await _sent(
        previous=previous, current=HealthState.HEALTHY, rule=DISK_SPACE_LOW, on=_DOWNLOAD_TRACKING
    )
    assert sent == []


@pytest.mark.asyncio
async def test_the_disk_failing_on_a_node_without_a_floor_raises() -> None:
    with pytest.raises(ValueError, match="download tracking amuled: no disk floor for its alert"):
        await _sent(
            previous=HealthState.HEALTHY,
            current=HealthState.FAILING,
            rule=DISK_SPACE_LOW,
            on=_DOWNLOAD_TRACKING,
            min_free_bytes=None,
        )
