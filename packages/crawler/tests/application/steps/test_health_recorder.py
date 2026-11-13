import pytest

from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_condition import Health, Outcome
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.status_reading import CLIENT_UNREACHABLE, ClientNotAnswering
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine

_NO_ANSWER = Outcome.failed(ClientNotAnswering())
type _Received = list[tuple[str, HealthTransition]]


async def _record(*outcomes: Outcome) -> tuple[FakeLogger, _Received, Component]:
    logger, received = FakeLogger(), []

    async def first(transition: HealthTransition) -> None:
        received.append(("first", transition))

    async def second(transition: HealthTransition) -> None:
        received.append(("second", transition))

    amuled = ClientName("amuled")
    client = Component(name="client amuled", client_name=amuled, conditions=(CLIENT_UNREACHABLE,))
    recorder = HealthRecorder(logger=logger, subscribers=(first, second))
    for outcome in outcomes:
        await recorder.record(outcome, on=client, condition=CLIENT_UNREACHABLE)
    return logger, received, client


@pytest.mark.asyncio
async def test_turning_failing_is_one_warning_line_then_each_subscriber_in_order() -> None:
    logger, received, client = await _record(_NO_ANSWER, _NO_ANSWER, _NO_ANSWER)
    assert logger.lines == [
        LoggedLine(level="warning", message="client amuled, unreachable: unknown to failing")
    ]
    unknown, failing = Health.UNKNOWN, Health.FAILING
    transition = HealthTransition(
        component=client, condition=CLIENT_UNREACHABLE, previous=unknown, current=failing
    )
    assert received == [("first", transition), ("second", transition)]


@pytest.mark.asyncio
async def test_any_other_transition_is_one_info_line() -> None:
    logger, _, _ = await _record(*[Outcome.success()] * 3)
    assert logger.lines == [
        LoggedLine(level="info", message="client amuled, unreachable: unknown to healthy")
    ]


@pytest.mark.asyncio
async def test_an_outcome_changing_no_health_logs_and_passes_on_nothing() -> None:
    logger, received, _ = await _record(Outcome.success(), Outcome.success())
    assert (logger.lines, received) == ([], [])
