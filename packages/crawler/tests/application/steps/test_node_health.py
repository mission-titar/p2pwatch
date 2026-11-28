import pytest

from p2pwatch.adapters.driven.in_memory_open_alert_store import InMemoryOpenAlertStore
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.domain.health.external_dependency import HealthAlert
from p2pwatch.domain.identifiers import ClientName, NodeId
from p2pwatch.domain.observability.events import WorksHealthyAgain, WorksStillFailing
from p2pwatch.domain.observability.notification import Notification, RelayedLogLine
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.status_reading import CLIENT_UNREACHABLE, client_dependency
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
    """The node's health over the aMule client, its log, the alerts it dispatches and keeps open."""

    def __init__(self) -> None:
        self.logger = FakeLogger()
        self.observability = ObservabilityOverFakes()
        self.open_alerts = InMemoryOpenAlertStore()
        self.amule = client_dependency(ClientName("amuled"), node_id=_NODE_ID)
        self.node_health = NodeHealth(
            logger=self.logger,
            observability_dispatcher=self.observability.dispatcher,
            open_alert_writer=self.open_alerts,
        )

    async def check(self, *, detected: bool, times: int) -> None:
        for _ in range(times):
            await self.node_health.record(on=self.amule, rule=CLIENT_UNREACHABLE, detected=detected)

    def alerts(self) -> list[Notification]:
        return [notification for _, notification in self.observability.notifications]

    def messages(self) -> list[str]:
        return [n.message for n in self.alerts() if isinstance(n, RelayedLogLine)]


def _unrepaired(work: str) -> HealthAlert:
    """The supervisor's alert on the aMule client left unrepaired, ``work`` failing."""
    return HealthAlert(
        about="client amuled",
        when_failing=WorksStillFailing(
            object_name="client amuled", works=(work,), rebuilds=3, node_id=_NODE_ID
        ),
        when_healthy_again=WorksHealthyAgain(object_name="client amuled", node_id=_NODE_ID),
    )


_UNREPAIRED = _unrepaired("search 'keroro' amuled ed2k")
_STILL_FAILING = "client amuled: search 'keroro' amuled ed2k still failing after 3 rebuilds"
_HEALTHY_AGAIN = "client amuled: every work healthy again"


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


async def test_the_client_healthy_from_its_first_checks_sends_nothing() -> None:
    amule_health = _AmuleHealth()
    await amule_health.check(detected=False, times=3)
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


async def test_an_alert_opened_dispatches_its_opening() -> None:
    amule_health = _AmuleHealth()
    await amule_health.node_health.open_alert(_UNREPAIRED)
    assert amule_health.messages() == [_STILL_FAILING]


async def test_an_alert_opened_again_while_open_dispatches_nothing_more() -> None:
    amule_health = _AmuleHealth()
    await amule_health.node_health.open_alert(_UNREPAIRED)
    await amule_health.node_health.open_alert(_unrepaired("search 'titar' amuled kad"))
    assert amule_health.messages() == [_STILL_FAILING]


async def test_an_alert_ended_dispatches_the_end_of_the_one_opened() -> None:
    amule_health = _AmuleHealth()
    await amule_health.node_health.open_alert(_UNREPAIRED)
    await amule_health.node_health.end_alert(about="client amuled")
    assert amule_health.messages() == [_STILL_FAILING, _HEALTHY_AGAIN]


async def test_an_alert_ended_again_once_ended_dispatches_nothing_more() -> None:
    amule_health = _AmuleHealth()
    await amule_health.node_health.open_alert(_UNREPAIRED)
    await amule_health.node_health.end_alert(about="client amuled")
    await amule_health.node_health.end_alert(about="client amuled")
    assert amule_health.messages() == [_STILL_FAILING, _HEALTHY_AGAIN]


async def test_an_alert_ended_opens_again_with_its_opening() -> None:
    amule_health = _AmuleHealth()
    await amule_health.node_health.open_alert(_UNREPAIRED)
    await amule_health.node_health.end_alert(about="client amuled")
    await amule_health.node_health.open_alert(_UNREPAIRED)
    assert amule_health.messages() == [_STILL_FAILING, _HEALTHY_AGAIN, _STILL_FAILING]


async def test_an_alert_opened_is_set_open_after_the_ones_opened_before() -> None:
    amule_health = _AmuleHealth()
    await amule_health.check(detected=True, times=3)
    await amule_health.node_health.open_alert(_UNREPAIRED)
    open_alerts = amule_health.open_alerts.read_open_alerts()
    assert [alert.about for alert in open_alerts] == ["client amuled, unreachable", "client amuled"]


async def test_an_alert_ended_is_set_open_no_more() -> None:
    amule_health = _AmuleHealth()
    await amule_health.node_health.open_alert(_UNREPAIRED)
    await amule_health.check(detected=True, times=3)
    await amule_health.check(detected=False, times=9)
    assert amule_health.open_alerts.read_open_alerts() == (_UNREPAIRED,)
