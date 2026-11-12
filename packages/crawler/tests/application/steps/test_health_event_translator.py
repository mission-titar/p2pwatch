"""The health event translator: the transitions of the readings' conditions become today's
connectivity events, an alert on entering its band, its end only on a return to healthy after it."""

import pytest

from p2pwatch.application.steps.health_event_translator import HealthEventTranslator
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.download.disk_space import DISK_SPACE_LOW, FreeSpaceBelowFloor
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_condition import BUGS, Health, HealthCondition
from p2pwatch.domain.health.outcome import Outcome
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.observability.notification import Notification, RelayedLogLine
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.search.searches_failed import SEARCHES_FAILED
from p2pwatch.domain.status_reading import (
    CHANNEL_NOT_CONNECTABLE,
    CHANNEL_NOT_CONNECTED,
    CLIENT_UNREACHABLE,
    CONNECTED_TO_NO_NETWORK,
    channel_component,
    client_component,
)
from p2pwatch.domain.work_components import download_tracking_component, webui_component
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier

_NODE_ID = NodeId("titar-node-1")
_CLIENT = client_component(ClientName("fake"))
_KAD = channel_component(client_name=ClientName("fake"), channel=Channel("kad"))
U, H, D, F = Health.UNKNOWN, Health.HEALTHY, Health.DEGRADED, Health.FAILING


async def _notified(
    *,
    previous: Health,
    current: Health,
    condition: HealthCondition = CLIENT_UNREACHABLE,
    component: Component = _CLIENT,
    outcome: Outcome | None = None,
) -> list[Notification]:
    notifier = FakeNotifier()
    translator = HealthEventTranslator(
        observability_dispatcher=ObservabilityDispatcher(
            logger=FakeLogger(),
            node_metric_writer=FakeNodeMetricStore(),
            notifier=notifier,
            notification_timeout_seconds=5.0,
        ),
        node_id=_NODE_ID,
    )
    await translator.translate(
        HealthTransition(
            component=component,
            condition=condition,
            previous=previous,
            current=current,
            outcome=outcome or Outcome.success(),
        )
    )
    return [notification for _, notification in notifier.calls]


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", [U, H])
async def test_the_client_entering_unreachable_alerts_with_today_s_duration(
    previous: Health,
) -> None:
    assert await _notified(previous=previous, current=F) == [
        RelayedLogLine(
            message="fake unreachable for 2 min", severity=Severity.WARNING, node_id=_NODE_ID
        )
    ]


@pytest.mark.asyncio
async def test_the_client_healthy_again_after_failing_ends_its_alert() -> None:
    assert await _notified(previous=F, current=H) == [
        RelayedLogLine(message="fake reachable again", severity=Severity.INFO, node_id=_NODE_ID)
    ]


@pytest.mark.asyncio
async def test_the_client_known_healthy_at_its_first_readings_sends_nothing() -> None:
    assert await _notified(previous=U, current=H) == []


def _warning(message: str) -> RelayedLogLine:
    return RelayedLogLine(message=message, severity=Severity.WARNING, node_id=_NODE_ID)


def _info(message: str) -> RelayedLogLine:
    return RelayedLogLine(message=message, severity=Severity.INFO, node_id=_NODE_ID)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("condition", "band", "alert", "end"),
    [
        (CHANNEL_NOT_CONNECTED, F, "off its network for 5 min", "back on its network"),
        (CHANNEL_NOT_CONNECTABLE, D, "not connectable for 5 min", "connectable again"),
    ],
    ids=["not connected", "not connectable"],
)
async def test_a_channel_entering_its_band_alerts_and_leaving_it_ends_the_alert(
    *, condition: HealthCondition, band: Health, alert: str, end: str
) -> None:
    notified = [
        await _notified(previous=previous, current=current, condition=condition, component=_KAD)
        for previous, current in [(U, band), (H, band), (band, H), (U, H)]
    ]
    assert notified == [
        [_warning(f"fake kad: {alert}")],
        [_warning(f"fake kad: {alert}")],
        [_info(f"fake kad: {end}")],
        [],
    ]


@pytest.mark.asyncio
async def test_a_channel_s_condition_on_a_component_naming_no_channel_sends_nothing() -> None:
    assert await _notified(previous=H, current=F, condition=CHANNEL_NOT_CONNECTED) == []


class _Other(DeclaredFailure):
    """A reason no event translates."""


@pytest.mark.asyncio
async def test_a_condition_no_event_names_sends_nothing() -> None:
    other = HealthCondition(
        name="other",
        source=CLIENT_UNREACHABLE.source,
        counting=_Other,
        failing=CLIENT_UNREACHABLE.failing,
        degraded=None,
    )
    assert await _notified(previous=H, current=F, condition=other) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("previous", "current"), [(U, D), (D, F), (F, H)])
@pytest.mark.parametrize(
    ("condition", "component"),
    [
        (BUGS, _KAD),
        (SEARCHES_FAILED, _KAD),
        (CONNECTED_TO_NO_NETWORK, download_tracking_component(ClientName("fake"))),
        (BUGS, webui_component()),
    ],
    ids=[
        "a channel's bugs",
        "a channel's searches failed",
        "connected to no network",
        "the webui's bugs",
    ],
)
async def test_a_condition_without_an_event_of_today_sends_nothing(
    *, previous: Health, current: Health, condition: HealthCondition, component: Component
) -> None:
    assert (
        await _notified(
            previous=previous, current=current, condition=condition, component=component
        )
        == []
    )


_DOWNLOAD_TRACKING = download_tracking_component(ClientName("fake"))


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", [U, H])
async def test_the_disk_entering_degraded_alerts_with_the_reading_that_entered_it(
    previous: Health,
) -> None:
    low = FreeSpaceBelowFloor(free_bytes=3 * 2**29, min_free_bytes=10 * 2**30)
    assert await _notified(
        previous=previous,
        current=D,
        condition=DISK_SPACE_LOW,
        component=_DOWNLOAD_TRACKING,
        outcome=Outcome.declared(low),
    ) == [_warning("download disk low: 1.5 GiB free, under the 10.0 GiB floor (no new download)")]


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", [U, D])
async def test_the_disk_healthy_sends_nothing_as_today(previous: Health) -> None:
    assert (
        await _notified(
            previous=previous, current=H, condition=DISK_SPACE_LOW, component=_DOWNLOAD_TRACKING
        )
        == []
    )
