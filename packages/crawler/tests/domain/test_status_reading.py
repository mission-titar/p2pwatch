import dataclasses
from datetime import timedelta

import pytest

from p2pwatch.domain.health.health_rule import HealthState
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.status_reading import (
    CHANNEL_NOT_CONNECTABLE,
    CHANNEL_NOT_CONNECTED,
    CLIENT_UNREACHABLE,
    SEARCHES_FAILED,
    STATUS_PERIOD,
    ChannelStatus,
    ClientStatus,
    channel_component,
    client_component,
    is_reading_fresh,
)
from p2pwatch.domain.work_components import BUGS
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


def test_the_client_s_component_is_named_after_it_and_fails_at_3_unanswered_readings() -> None:
    client = client_component(ClientName("amuled"))
    assert client.name == "client amuled"
    transitions = [client.record(rule=CLIENT_UNREACHABLE, detected=True) for _ in range(3)]
    assert [t and t.current for t in transitions] == [None, None, HealthState.FAILING]


def test_a_channel_s_component_is_named_after_it_and_holds_both_channel_rules() -> None:
    kad = channel_component(client_name=ClientName("amuled"), channel=Channel("kad"))
    assert kad.name == "channel amuled kad"
    # A rule the component lacks would raise at its first record.
    assert kad.record(rule=CHANNEL_NOT_CONNECTED, detected=True) is None
    assert kad.record(rule=CHANNEL_NOT_CONNECTABLE, detected=True) is None


def test_a_channel_s_component_fails_at_the_third_bug_in_a_row_of_its_searches() -> None:
    kad = channel_component(client_name=ClientName("amuled"), channel=Channel("kad"))
    transitions = [kad.record(rule=BUGS, detected=True) for _ in range(3)]
    assert [t and t.current for t in transitions] == [None, None, HealthState.FAILING]


def test_a_channel_s_searches_fail_at_3_refused_in_a_row_and_heal_under_2_in_the_last_10() -> None:
    kad = channel_component(client_name=ClientName("amuled"), channel=Channel("kad"))

    refused = [kad.record(rule=SEARCHES_FAILED, detected=True) for _ in range(3)]
    ran = [kad.record(rule=SEARCHES_FAILED, detected=False) for _ in range(9)]

    assert [t and t.current for t in refused] == [None, None, HealthState.FAILING]
    # The ninth search that ran leaves a single refusal among the last 10.
    assert [t and t.current for t in ran] == [*[None] * 8, HealthState.HEALTHY]
