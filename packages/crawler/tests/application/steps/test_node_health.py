import pytest

from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.domain.health.health_rule import HealthRule
from p2pwatch.domain.identifiers import ClientName, NodeId
from p2pwatch.domain.observability.notification import Notification, RelayedLogLine
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.status_reading import (
    CLIENT_UNREACHABLE,
    CONNECTED_TO_NO_NETWORK,
    client_dependency,
)
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

pytestmark = pytest.mark.asyncio

_NODE_ID = NodeId("titar-node-1")
_UNREACHABLE = RelayedLogLine(
    message="amuled unreachable for 2 min",
    detail="impact: no search, no download",
    severity=Severity.WARNING,
    node_id=_NODE_ID,
)
_REACHABLE_AGAIN = RelayedLogLine(
    message="amuled reachable again", severity=Severity.INFO, node_id=_NODE_ID
)


class _AmuleHealth:
    """The node's health over the aMule client, its log and the alerts it dispatches."""

    def __init__(self) -> None:
        self.logger = FakeLogger()
        self.observability = ObservabilityOverFakes()
        self.amule = client_dependency(ClientName("amuled"), node_id=_NODE_ID)
        self._node_health = NodeHealth(
            logger=self.logger, observability_dispatcher=self.observability.dispatcher
        )

    async def check(
        self, *, detected: bool, times: int, rule: HealthRule = CLIENT_UNREACHABLE
    ) -> None:
        for _ in range(times):
            await self._node_health.record(on=self.amule, rule=rule, detected=detected)

    def alerts(self) -> list[Notification]:
        return [notification for _, notification in self.observability.notifications]


async def test_the_client_turning_failing_is_logged_as_one_warning() -> None:
    amule_health = _AmuleHealth()
    await amule_health.check(detected=True, times=3)
    assert amule_health.logger.lines == [
        LoggedLine(level="warning", message="client amuled, unreachable: unknown to failing")
    ]


async def test_the_client_turning_healthy_is_logged_as_one_info_line() -> None:
    amule_health = _AmuleHealth()
    await amule_health.check(detected=False, times=3)
    assert amule_health.logger.lines == [
        LoggedLine(level="info", message="client amuled, unreachable: unknown to healthy")
    ]


async def test_the_client_turning_failing_then_healthy_again_sends_its_alert_then_its_end() -> None:
    amule_health = _AmuleHealth()
    await amule_health.check(detected=True, times=3)
    await amule_health.check(detected=False, times=9)
    assert amule_health.alerts() == [_UNREACHABLE, _REACHABLE_AGAIN]


async def test_a_change_under_a_rule_without_an_alert_is_logged_and_sends_nothing() -> None:
    amule_health = _AmuleHealth()
    await amule_health.check(detected=True, times=6, rule=CONNECTED_TO_NO_NETWORK)
    message = "client amuled, connected to no network: unknown to failing"
    assert amule_health.logger.lines == [LoggedLine(level="warning", message=message)]
    assert amule_health.alerts() == []


async def test_a_check_that_changes_nothing_is_neither_logged_nor_alerted() -> None:
    amule_health = _AmuleHealth()
    await amule_health.check(detected=False, times=2)
    assert amule_health.logger.lines == []
    assert amule_health.alerts() == []


async def test_nothing_is_awaited_between_a_rule_turning_failing_and_its_alert() -> None:
    # The rule is already failing once its alert is left: a turn cut between would lose it.
    amule_health = _AmuleHealth()
    await amule_health.check(detected=True, times=2)
    amule_health.observability.watch_for_a_suspension()

    await amule_health.check(detected=True, times=1)

    assert amule_health.alerts() == [_UNREACHABLE]
    assert amule_health.observability.suspended_before_each_leave == [False]
