import pytest

from p2pwatch.application.steps.health_alerter import HealthAlerter
from p2pwatch.domain.health.external_dependency import HealthAlert, HealthTransition
from p2pwatch.domain.health.health_rule import HealthState
from p2pwatch.domain.identifiers import ClientName, NodeId
from p2pwatch.domain.observability.events import ClientReachableAgain, ClientUnreachableLasting
from p2pwatch.domain.observability.notification import Notification, RelayedLogLine
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.status_reading import CLIENT_UNREACHABLE, client_dependency
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

pytestmark = pytest.mark.asyncio

_NODE_ID = NodeId("titar-node-1")
_AMULED = ClientName("amuled")
_UNREACHABLE_ALERT = HealthAlert(
    when_failing=ClientUnreachableLasting(
        client_name=_AMULED, unreachable_for_seconds=120.0, node_id=_NODE_ID
    ),
    when_healthy_again=ClientReachableAgain(client_name=_AMULED, node_id=_NODE_ID),
)
_UNREACHABLE = RelayedLogLine(
    message="amuled unreachable for 2 min", severity=Severity.WARNING, node_id=_NODE_ID
)


def _turning_failing(alert: HealthAlert | None) -> HealthTransition:
    return HealthTransition(
        dependency=client_dependency(_AMULED, node_id=_NODE_ID),
        rule=CLIENT_UNREACHABLE,
        alert=alert,
        previous=HealthState.HEALTHY,
        current=HealthState.FAILING,
    )


async def _sent(transition: HealthTransition) -> list[Notification]:
    observability = ObservabilityOverFakes()
    await HealthAlerter(observability_dispatcher=observability.dispatcher).send(transition)
    return [notification for _, notification in observability.notifications]


async def test_a_change_whose_rule_has_an_alert_sends_it() -> None:
    assert await _sent(_turning_failing(_UNREACHABLE_ALERT)) == [_UNREACHABLE]


async def test_a_change_whose_rule_has_no_alert_sends_nothing() -> None:
    assert await _sent(_turning_failing(None)) == []


async def test_nothing_is_awaited_between_a_rule_turning_failing_and_its_alert() -> None:
    # The rule is already failing once its alert is left: a turn cut between would lose it.
    observability = ObservabilityOverFakes()
    alerter = HealthAlerter(observability_dispatcher=observability.dispatcher)
    observability.watch_for_a_suspension()

    await alerter.send(_turning_failing(_UNREACHABLE_ALERT))

    assert [notification for _, notification in observability.notifications] == [_UNREACHABLE]
    assert observability.suspended_before_each_leave == [False]
