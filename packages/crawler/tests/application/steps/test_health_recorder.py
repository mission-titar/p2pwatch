"""The health recorder: every outcome goes through it, each transition logged in one line and handed
to every subscriber, in order."""

import pytest

from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.domain.health.component import Component, ComponentLabels, HealthTransition
from p2pwatch.domain.health.health_condition import Health
from p2pwatch.domain.health.outcome import Outcome
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.status_reading import (
    CLIENT_UNREACHABLE,
    STATUS_API_ANSWER,
    ClientNotAnswering,
)
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine


def _client() -> Component:
    return Component(
        name="client amuled",
        labels=ComponentLabels(client_name=ClientName("amuled")),
        conditions=(CLIENT_UNREACHABLE,),
    )


class _Subscribers:
    """Two subscribers writing to one list, so their order shows."""

    def __init__(self) -> None:
        self.received: list[tuple[str, HealthTransition]] = []

    async def first(self, transition: HealthTransition) -> None:
        self.received.append(("first", transition))

    async def second(self, transition: HealthTransition) -> None:
        self.received.append(("second", transition))


async def _record(*outcomes: Outcome) -> tuple[FakeLogger, _Subscribers, Component]:
    logger, subscribers, client = FakeLogger(), _Subscribers(), _client()
    recorder = HealthRecorder(logger=logger, subscribers=(subscribers.first, subscribers.second))
    for outcome in outcomes:
        await recorder.record(outcome, on=client, by=STATUS_API_ANSWER)
    return logger, subscribers, client


_NO_ANSWER = Outcome.declared(ClientNotAnswering())


@pytest.mark.asyncio
async def test_a_transition_reaches_every_subscriber_in_order() -> None:
    _, subscribers, client = await _record(_NO_ANSWER, _NO_ANSWER, _NO_ANSWER)
    transition = HealthTransition(
        component=client,
        condition=CLIENT_UNREACHABLE,
        previous=Health.UNKNOWN,
        current=Health.FAILING,
    )
    assert subscribers.received == [("first", transition), ("second", transition)]


@pytest.mark.asyncio
async def test_a_condition_entering_failing_is_one_warning_line() -> None:
    logger, _, _ = await _record(_NO_ANSWER, _NO_ANSWER, _NO_ANSWER)
    assert logger.lines == [
        LoggedLine(level="warning", message="client amuled, unreachable: unknown to failing")
    ]


@pytest.mark.asyncio
async def test_any_other_transition_is_one_info_line() -> None:
    logger, _, _ = await _record(*[Outcome.success()] * 3)
    assert logger.lines == [
        LoggedLine(level="info", message="client amuled, unreachable: unknown to healthy")
    ]


@pytest.mark.asyncio
async def test_an_outcome_changing_no_condition_logs_and_hands_nothing() -> None:
    logger, subscribers, _ = await _record(Outcome.success(), Outcome.success())
    assert (logger.lines, subscribers.received) == ([], [])
