import asyncio
from dataclasses import replace

import pytest

from p2pwatch.application.steps.health_alerter import (
    ChannelAlert,
    ClientAlert,
    DiskAlert,
    HealthAlerter,
)
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.download.disk_space import (
    CONNECTED_TO_NO_NETWORK,
    DISK_SPACE_LOW,
    download_tracking_component,
)
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_rule import HealthRule, HealthState
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.observability.notification import Notification, RelayedLogLine
from p2pwatch.domain.observability.notification_sends import (
    SENDS_FAILED,
    notification_service_components,
)
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.status_reading import (
    CHANNEL_NOT_CONNECTABLE,
    CHANNEL_NOT_CONNECTED,
    CLIENT_UNREACHABLE,
    SEARCHES_FAILED,
    channel_component,
    client_component,
)
from p2pwatch.domain.work_components import BUGS, status_reading_component, webui_component
from tests.fakes.adapters.driven.fake_held_notifier import FakeHeldNotifier
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE, FakeNotifier

_NODE_ID = NodeId("titar-node-1")
_UNREACHABLE = RelayedLogLine(
    message="amuled unreachable for 2 min", severity=Severity.WARNING, node_id=_NODE_ID
)
_REACHABLE_AGAIN = RelayedLogLine(
    message="amuled reachable again", severity=Severity.INFO, node_id=_NODE_ID
)


_AMULE = client_component(ClientName("amuled"))
_ED2K = channel_component(client_name=ClientName("amuled"), channel=Channel("ed2k"))
_KAD = channel_component(client_name=ClientName("amuled"), channel=Channel("kad"))
_DOWNLOAD_TRACKING = download_tracking_component(ClientName("amuled"))
_TEN_GIB = 10 * 2**30
_DISK = DiskAlert(part=_DOWNLOAD_TRACKING, min_free_bytes=_TEN_GIB)
_NOTIFICATION_SERVICE_PART = notification_service_components(ONE_SERVICE_PER_AUDIENCE)[
    ONE_SERVICE_PER_AUDIENCE[0]
]


async def _sent(
    *,
    previous: HealthState,
    current: HealthState,
    rule: HealthRule = CLIENT_UNREACHABLE,
    on: Component = _AMULE,
    disk: DiskAlert | None = _DISK,
) -> list[Notification]:
    """The notifications sent when the health of ``on`` under ``rule`` changes, the alerter
    given the client's part, both its channels' and ``disk``."""
    notifier = FakeNotifier()
    dispatcher = ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=FakeNodeMetricStore(),
        current_notifier=lambda: notifier,
        notification_timeout_seconds=5.0,
        record_check=NodeHealth(logger=FakeLogger(), subscribers=()).record,
        service_components=notification_service_components(notifier.services()),
    )
    alerter = _alerter(dispatcher, disk=disk)
    await alerter.send(
        HealthTransition(component=on, rule=rule, previous=previous, current=current)
    )
    return [notification for _, notification in notifier.calls]


def _alerter(dispatcher: ObservabilityDispatcher, *, disk: DiskAlert | None) -> HealthAlerter:
    amuled = ClientName("amuled")
    return HealthAlerter(
        observability_dispatcher=dispatcher,
        node_id=_NODE_ID,
        client=ClientAlert(part=_AMULE, client_name=amuled),
        channels=[
            ChannelAlert(part=_ED2K, client_name=amuled, channel=Channel("ed2k")),
            ChannelAlert(part=_KAD, client_name=amuled, channel=Channel("kad")),
        ],
        disk=disk,
    )


@pytest.mark.asyncio
async def test_the_client_failing_at_its_first_readings_sends_unreachable_for_2_min() -> None:
    assert await _sent(previous=HealthState.UNKNOWN, current=HealthState.FAILING) == [_UNREACHABLE]


@pytest.mark.asyncio
async def test_the_client_failing_after_being_healthy_sends_unreachable_for_2_min() -> None:
    assert await _sent(previous=HealthState.HEALTHY, current=HealthState.FAILING) == [_UNREACHABLE]


@pytest.mark.asyncio
async def test_the_client_healthy_again_sends_reachable_again() -> None:
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
async def test_a_rule_it_has_no_alert_for_raises(
    *, previous: HealthState, current: HealthState
) -> None:
    other = replace(CLIENT_UNREACHABLE, name="other")
    with pytest.raises(
        ValueError, match="^client amuled, other: no alert for this part under this rule$"
    ):
        await _sent(previous=previous, current=current, rule=other)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rule", "on"),
    [
        (BUGS, status_reading_component(ClientName("amuled"))),
        (BUGS, _KAD),
        (BUGS, _DOWNLOAD_TRACKING),
        (BUGS, webui_component()),
        (SEARCHES_FAILED, _KAD),
        (CONNECTED_TO_NO_NETWORK, _DOWNLOAD_TRACKING),
        # An alert about the notifier would be sent through the notifier itself.
        (BUGS, _NOTIFICATION_SERVICE_PART),
        (SENDS_FAILED, _NOTIFICATION_SERVICE_PART),
    ],
    ids=[
        "a task's bugs",
        "a channel's bugs",
        "download tracking's bugs",
        "the webui's bugs",
        "a channel's searches failed",
        "download tracking connected to no network",
        "a notification service's bugs",
        "a notification service's sends failed",
    ],
)
@pytest.mark.parametrize(
    ("previous", "current"),
    [
        (HealthState.UNKNOWN, HealthState.FAILING),
        (HealthState.HEALTHY, HealthState.FAILING),
        (HealthState.FAILING, HealthState.HEALTHY),
    ],
)
async def test_a_part_failing_or_healthy_again_under_a_rule_without_an_alert_sends_nothing(
    *, rule: HealthRule, on: Component, previous: HealthState, current: HealthState
) -> None:
    # The log line of the change is all the operator gets of it.
    assert await _sent(previous=previous, current=current, rule=rule, on=on) == []


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
async def test_each_channel_s_alert_names_its_own_channel() -> None:
    sent = await _sent(
        previous=HealthState.HEALTHY,
        current=HealthState.FAILING,
        rule=CHANNEL_NOT_CONNECTED,
        on=_ED2K,
    )
    assert sent == [
        RelayedLogLine(
            message="amuled ed2k: off its network for 5 min",
            severity=Severity.WARNING,
            node_id=_NODE_ID,
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rule", "on", "message"),
    [
        (CLIENT_UNREACHABLE, webui_component(), "webui, unreachable"),
        (CLIENT_UNREACHABLE, _KAD, "channel amuled kad, unreachable"),
        (CHANNEL_NOT_CONNECTED, _AMULE, "client amuled, not connected"),
        (DISK_SPACE_LOW, _KAD, "channel amuled kad, disk space low"),
    ],
    ids=[
        "the client's rule on the webui",
        "the client's rule on a channel",
        "a channel's rule on the client",
        "the disk's rule on a channel",
    ],
)
@pytest.mark.parametrize(
    "current", [HealthState.FAILING, HealthState.HEALTHY], ids=["its alert", "its end"]
)
async def test_a_rule_with_an_alert_on_a_part_it_was_not_given_for_it_raises(
    *, rule: HealthRule, on: Component, message: str, current: HealthState
) -> None:
    previous = HealthState.HEALTHY if current is HealthState.FAILING else HealthState.FAILING

    with pytest.raises(ValueError, match=f"^{message}: no alert for this part under this rule$"):
        await _sent(previous=previous, current=current, rule=rule, on=on)


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
@pytest.mark.parametrize(
    "current", [HealthState.FAILING, HealthState.HEALTHY], ids=["its alert", "its end"]
)
async def test_the_disk_s_rule_on_a_node_that_downloads_nothing_raises(
    current: HealthState,
) -> None:
    previous = HealthState.HEALTHY if current is HealthState.FAILING else HealthState.FAILING
    message = "^download tracking amuled, disk space low: no alert for this part under this rule$"

    with pytest.raises(ValueError, match=message):
        await _sent(
            previous=previous,
            current=current,
            rule=DISK_SPACE_LOW,
            on=_DOWNLOAD_TRACKING,
            disk=None,
        )


@pytest.mark.asyncio
async def test_an_alert_whose_turn_is_cut_mid_send_is_still_sent() -> None:
    # The rule is already failing once its alert is sent: a send lost here is never sent again.
    notifier = FakeHeldNotifier()
    dispatcher = ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=FakeNodeMetricStore(),
        current_notifier=lambda: notifier,
        notification_timeout_seconds=5.0,
        record_check=NodeHealth(logger=FakeLogger(), subscribers=()).record,
        service_components=notification_service_components(notifier.services()),
    )
    alerter = _alerter(dispatcher, disk=_DISK)
    transition = HealthTransition(
        component=_AMULE,
        rule=CLIENT_UNREACHABLE,
        previous=HealthState.HEALTHY,
        current=HealthState.FAILING,
    )
    turn = asyncio.create_task(alerter.send(transition))
    await notifier.reached.wait()

    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn
    notifier.released.set()
    await notifier.wait_until_sent(timeout_seconds=1.0)

    assert [notification for _, notification in notifier.calls] == [_UNREACHABLE]
