"""The health event translator: the transitions of the readings' conditions become today's
connectivity events, an alert on entering failing, its end only on a return to healthy after it."""

import pytest

from p2pwatch.application.steps.health_event_translator import HealthEventTranslator
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.component import Component, ComponentLabels, HealthTransition
from p2pwatch.domain.health.health_condition import Health, HealthCondition
from p2pwatch.domain.identifiers import ClientName, NodeId
from p2pwatch.domain.observability.notification import Notification, RelayedLogLine
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.status_reading import CLIENT_UNREACHABLE
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier

_NODE_ID = NodeId("titar-node-1")
_CLIENT = Component(
    name="client fake",
    labels=ComponentLabels(client_name=ClientName("fake")),
    conditions=(CLIENT_UNREACHABLE,),
)
U, H, F = Health.UNKNOWN, Health.HEALTHY, Health.FAILING


async def _notified(
    *, previous: Health, current: Health, condition: HealthCondition = CLIENT_UNREACHABLE
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
        HealthTransition(component=_CLIENT, condition=condition, previous=previous, current=current)
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


class _Other(DeclaredFailure):
    """A reason no event translates."""


@pytest.mark.asyncio
async def test_a_condition_no_event_names_sends_nothing() -> None:
    other = HealthCondition(
        name="other",
        source=CLIENT_UNREACHABLE.source,
        counting=_Other,
        failing=CLIENT_UNREACHABLE.failing,
    )
    assert await _notified(previous=H, current=F, condition=other) == []
