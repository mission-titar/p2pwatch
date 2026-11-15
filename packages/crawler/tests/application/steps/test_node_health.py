import pytest

from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_rule import HealthState
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.status_reading import CLIENT_UNREACHABLE
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine


class _Subscribers:
    """Two subscribers writing to one list, so their order shows."""

    def __init__(self) -> None:
        self.received: list[tuple[str, HealthTransition]] = []

    async def first(self, transition: HealthTransition) -> None:
        self.received.append(("first", transition))

    async def second(self, transition: HealthTransition) -> None:
        self.received.append(("second", transition))


class _AmuleHealth:
    """The node's health over the aMule client, its log and its two subscribers."""

    def __init__(self) -> None:
        self.logger = FakeLogger()
        self.subscribers = _Subscribers()
        self.amule = Component(
            name="client amuled",
            client_name=ClientName("amuled"),
            rules=(CLIENT_UNREACHABLE,),
        )
        self._node_health = NodeHealth(
            logger=self.logger, subscribers=(self.subscribers.first, self.subscribers.second)
        )

    async def check(self, *, detected: bool, times: int) -> None:
        for _ in range(times):
            await self._node_health.record(
                on=self.amule, rule=CLIENT_UNREACHABLE, detected=detected
            )


@pytest.mark.asyncio
async def test_the_client_turning_failing_is_logged_as_one_warning() -> None:
    amule_health = _AmuleHealth()
    await amule_health.check(detected=True, times=3)
    assert amule_health.logger.lines == [
        LoggedLine(level="warning", message="client amuled, unreachable: unknown to failing")
    ]


@pytest.mark.asyncio
async def test_the_client_turning_healthy_is_logged_as_one_info_line() -> None:
    amule_health = _AmuleHealth()
    await amule_health.check(detected=False, times=3)
    assert amule_health.logger.lines == [
        LoggedLine(level="info", message="client amuled, unreachable: unknown to healthy")
    ]


@pytest.mark.asyncio
async def test_each_change_reaches_every_subscriber_in_order() -> None:
    amule_health = _AmuleHealth()
    await amule_health.check(detected=True, times=3)
    change = HealthTransition(
        component=amule_health.amule,
        rule=CLIENT_UNREACHABLE,
        previous=HealthState.UNKNOWN,
        current=HealthState.FAILING,
    )
    assert amule_health.subscribers.received == [("first", change), ("second", change)]


@pytest.mark.asyncio
async def test_a_check_that_changes_nothing_is_neither_logged_nor_passed_on() -> None:
    amule_health = _AmuleHealth()
    await amule_health.check(detected=False, times=2)
    assert amule_health.logger.lines == []
    assert amule_health.subscribers.received == []
