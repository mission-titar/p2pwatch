import dataclasses
from datetime import timedelta

import pytest

from p2pwatch.domain.client_errors import SearchFailedError
from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.component import Component, ComponentLabels
from p2pwatch.domain.health.health_condition import ConditionWindow, Health, HealthCondition
from p2pwatch.domain.health.outcome import UNITS_OF_WORK, Outcome, OutcomeSource
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.searches_failed import SEARCHES
from p2pwatch.domain.status_reading import (
    CHANNEL_NOT_CONNECTABLE,
    CHANNEL_NOT_CONNECTED,
    CLIENT_UNREACHABLE,
    STATUS_API_ANSWER,
    STATUS_CONNECTABLE_FIELD,
    STATUS_CONNECTED_FIELD,
    STATUS_PERIOD,
    ChannelNotConnectable,
    ChannelNotConnected,
    ChannelStatus,
    ClientNotAnswering,
    ClientStatus,
    channel_component,
    client_component,
    is_reading_fresh,
    lasting_at_entry,
)
from tests.support.domain.value_bounds import NOT_WELL_FORMED_TEXTS, WELL_FORMED_TEXTS


def test_a_reading_stays_fresh_for_two_status_periods() -> None:
    assert is_reading_fresh(timedelta(0))
    assert is_reading_fresh(2 * STATUS_PERIOD)


def test_a_reading_older_than_two_status_periods_is_not_fresh() -> None:
    assert not is_reading_fresh(2 * STATUS_PERIOD + timedelta(microseconds=1))


def test_a_client_status_is_frozen_and_holds_its_channels() -> None:
    kad = ChannelStatus(channel=Channel("kad"), connected=True, connectable=None)
    status = ClientStatus(version="3.0.1", channels=(kad,))

    assert status.channels[0].connectable is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        kad.connected = False  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        status.version = None  # type: ignore[misc]


@pytest.mark.parametrize("version", NOT_WELL_FORMED_TEXTS)
def test_a_client_status_refuses_a_version_that_is_not_valid_utf8(version: str) -> None:
    with pytest.raises(ValueError, match="^a client status's version is not valid UTF-8$"):
        ClientStatus(version=version, channels=())


@pytest.mark.parametrize("version", [*WELL_FORMED_TEXTS, None])
def test_a_client_status_holds_a_valid_non_ascii_version_or_none(version: str | None) -> None:
    assert ClientStatus(version=version, channels=()).version == version


@pytest.mark.parametrize(
    ("condition", "reason", "entered"),
    [
        (CLIENT_UNREACHABLE, ClientNotAnswering, [Health.UNKNOWN] * 2 + [Health.FAILING]),
        (CHANNEL_NOT_CONNECTED, ChannelNotConnected, [Health.UNKNOWN] * 5 + [Health.FAILING]),
        (CHANNEL_NOT_CONNECTABLE, ChannelNotConnectable, [Health.UNKNOWN] * 5 + [Health.DEGRADED]),
    ],
    ids=["unreachable", "not connected", "not connectable"],
)
def test_a_reading_condition_enters_its_band_at_today_s_alert(
    *, condition: HealthCondition, reason: type[DeclaredFailure], entered: list[Health]
) -> None:
    window = ConditionWindow(condition=condition)
    healths = []
    for _ in entered:
        window = window.after(Outcome.declared(reason()))
        healths.append(window.health)
    assert healths == entered


def test_each_reading_condition_reads_its_own_field_of_the_reading() -> None:
    sources = [
        c.source for c in (CLIENT_UNREACHABLE, CHANNEL_NOT_CONNECTED, CHANNEL_NOT_CONNECTABLE)
    ]
    assert sources == [STATUS_API_ANSWER, STATUS_CONNECTED_FIELD, STATUS_CONNECTABLE_FIELD]


@pytest.mark.parametrize(
    ("condition", "lasted"),
    [(CLIENT_UNREACHABLE, 2), (CHANNEL_NOT_CONNECTED, 5), (CHANNEL_NOT_CONNECTABLE, 5)],
    ids=["unreachable", "not connected", "not connectable"],
)
def test_a_reading_condition_entering_its_band_has_lasted_a_period_per_reading_after_the_first(
    *, condition: HealthCondition, lasted: int
) -> None:
    # Today's alerts, "for 2 min" and "for 5 min".
    assert lasting_at_entry(condition) == timedelta(minutes=lasted)


def _conditions_entered(component: Component, *feeds: tuple[OutcomeSource, Outcome]) -> list[str]:
    """The conditions entering their band as each feed is recorded six times."""
    return [
        transition.condition.name
        for source, outcome in feeds
        for _ in range(6)
        for transition in component.record(outcome, by=source)
        if transition.current is not Health.HEALTHY
    ]


def test_a_client_s_component_is_judged_on_its_unreachable_condition() -> None:
    component = client_component(ClientName("amuled"))
    assert (component.name, component.labels) == (
        "client amuled",
        ComponentLabels(client_name=ClientName("amuled")),
    )
    assert _conditions_entered(
        component, (STATUS_API_ANSWER, Outcome.declared(ClientNotAnswering()))
    ) == ["unreachable"]


def test_a_channel_s_component_is_judged_on_its_two_fields_its_searches_and_its_turns_bugs() -> (
    None
):
    component = channel_component(client_name=ClientName("amuled"), channel=Channel("kad"))
    assert (component.name, component.labels) == (
        "channel amuled kad",
        ComponentLabels(client_name=ClientName("amuled"), channel=Channel("kad")),
    )
    assert _conditions_entered(
        component,
        (STATUS_CONNECTED_FIELD, Outcome.declared(ChannelNotConnected())),
        (STATUS_CONNECTABLE_FIELD, Outcome.declared(ChannelNotConnectable())),
        (SEARCHES, Outcome.declared(SearchFailedError("refused"))),
        (UNITS_OF_WORK, Outcome.bug("KeyError('channels')")),
    ) == ["not connected", "not connectable", "searches failed", "bugs"]
