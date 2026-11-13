import pytest

from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_condition import Health, Outcome
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.status_reading import CLIENT_UNREACHABLE, ClientNotAnswering
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine

_NO_ANSWER = Outcome.failed(ClientNotAnswering())
_ANSWER = Outcome.success()


class _Subscribers:
    """Two subscribers writing to one list, so their order shows."""

    def __init__(self) -> None:
        self.received: list[tuple[str, HealthTransition]] = []

    async def first(self, transition: HealthTransition) -> None:
        self.received.append(("first", transition))

    async def second(self, transition: HealthTransition) -> None:
        self.received.append(("second", transition))


class _Recorded:
    """A recorder over the aMule client, its log and its two subscribers."""

    def __init__(self) -> None:
        self.logger = FakeLogger()
        self.subscribers = _Subscribers()
        self.amule = Component(
            name="client amuled",
            client_name=ClientName("amuled"),
            conditions=(CLIENT_UNREACHABLE,),
        )
        self._recorder = HealthRecorder(
            logger=self.logger, subscribers=(self.subscribers.first, self.subscribers.second)
        )

    async def record(self, *outcomes: Outcome) -> None:
        for outcome in outcomes:
            await self._recorder.record(outcome, on=self.amule, condition=CLIENT_UNREACHABLE)


@pytest.mark.asyncio
async def test_the_client_starting_to_fail_is_logged_as_one_warning() -> None:
    recorded = _Recorded()
    await recorded.record(_NO_ANSWER, _NO_ANSWER, _NO_ANSWER)
    assert recorded.logger.lines == [
        LoggedLine(level="warning", message="client amuled, unreachable: unknown to failing")
    ]


@pytest.mark.asyncio
async def test_the_client_turning_healthy_is_logged_as_one_info_line() -> None:
    recorded = _Recorded()
    await recorded.record(_ANSWER, _ANSWER, _ANSWER)
    assert recorded.logger.lines == [
        LoggedLine(level="info", message="client amuled, unreachable: unknown to healthy")
    ]


@pytest.mark.asyncio
async def test_each_change_reaches_every_subscriber_in_order() -> None:
    recorded = _Recorded()
    await recorded.record(_NO_ANSWER, _NO_ANSWER, _NO_ANSWER)
    change = HealthTransition(
        component=recorded.amule,
        condition=CLIENT_UNREACHABLE,
        previous=Health.UNKNOWN,
        current=Health.FAILING,
    )
    assert recorded.subscribers.received == [("first", change), ("second", change)]


@pytest.mark.asyncio
async def test_an_outcome_that_changes_nothing_is_neither_logged_nor_passed_on() -> None:
    recorded = _Recorded()
    await recorded.record(_ANSWER, _ANSWER)
    assert recorded.logger.lines == []
    assert recorded.subscribers.received == []
