from dataclasses import replace

import pytest

from p2pwatch.application.steps.health_event_translator import HealthEventTranslator
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_condition import Health, HealthCondition
from p2pwatch.domain.identifiers import ClientName, NodeId
from p2pwatch.domain.observability.notification import Notification, RelayedLogLine
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.status_reading import CLIENT_UNREACHABLE
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier

_NODE_ID = NodeId("titar-node-1")
U, H, F = Health.UNKNOWN, Health.HEALTHY, Health.FAILING
type _Sent = list[tuple[str, Severity]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("condition", "previous", "current", "alerts"),
    [
        (CLIENT_UNREACHABLE, U, F, [("fake unreachable for 2 min", Severity.WARNING)]),
        (CLIENT_UNREACHABLE, H, F, [("fake unreachable for 2 min", Severity.WARNING)]),
        (CLIENT_UNREACHABLE, F, H, [("fake reachable again", Severity.INFO)]),
        (CLIENT_UNREACHABLE, U, H, []),  # healthy from its first readings: no alert to end
        (replace(CLIENT_UNREACHABLE, name="other"), H, F, []),  # a condition with no alert
    ],
)
async def test_the_unreachable_condition_alerts_on_failing_and_ends_on_healthy_again(
    *, condition: HealthCondition, previous: Health, current: Health, alerts: _Sent
) -> None:
    assert await _notified(condition, previous=previous, current=current) == [
        RelayedLogLine(message=message, severity=severity, node_id=_NODE_ID)
        for message, severity in alerts
    ]


async def _notified(
    condition: HealthCondition, *, previous: Health, current: Health
) -> list[Notification]:
    notifier = FakeNotifier()
    dispatcher = ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=FakeNodeMetricStore(),
        notifier=notifier,
        notification_timeout_seconds=5.0,
    )
    client = Component(name="client fake", client_name=ClientName("fake"), conditions=(condition,))
    await HealthEventTranslator(observability_dispatcher=dispatcher, node_id=_NODE_ID).translate(
        HealthTransition(component=client, condition=condition, previous=previous, current=current)
    )
    return [notification for _, notification in notifier.calls]
