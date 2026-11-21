import dataclasses
from datetime import timedelta

import pytest

from p2pwatch.domain.health.external_dependency import ExternalDependency, HealthAlert
from p2pwatch.domain.health.health_rule import HealthRule, HealthState
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.observability.events import (
    ChannelDegraded,
    ChannelField,
    ChannelRecovered,
    ClientPasswordAcceptedAgain,
    ClientPasswordRefused,
    ClientReachableAgain,
    ClientUnreachableLasting,
)
from p2pwatch.domain.status_reading import (
    CHANNEL_NOT_CONNECTABLE,
    CHANNEL_NOT_CONNECTED,
    CLIENT_UNREACHABLE,
    CONNECTED_TO_NO_NETWORK,
    PASSWORD_REFUSED,
    SEARCHES_FAILED,
    STATUS_PERIOD,
    ChannelStatus,
    ClientStatus,
    channel_dependency,
    client_dependency,
    is_reading_fresh,
)
from tests.support.domain.value_bounds import NOT_WELL_FORMED_TEXTS, WELL_FORMED_TEXTS

_AMULED = ClientName("amuled")
_KAD = Channel("kad")
_NODE_ID = NodeId("titar-node-1")


def _alert_of(dependency: ExternalDependency, *, rule: HealthRule) -> HealthAlert | None:
    """The alert ``rule`` carries on ``dependency``, read off its first change to failing."""
    *_, failing = [
        dependency.record(rule=rule, detected=True) for _ in range(rule.fails_at.among_last)
    ]
    assert failing is not None
    return failing.alert


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


def test_the_client_s_dependency_is_named_after_it_and_fails_at_3_unanswered_readings() -> None:
    client = client_dependency(_AMULED, node_id=_NODE_ID)
    assert (client.name, client.client_name, client.channel) == ("client amuled", "amuled", None)
    transitions = [client.record(rule=CLIENT_UNREACHABLE, detected=True) for _ in range(3)]
    assert [t and t.current for t in transitions] == [None, None, HealthState.FAILING]


def test_the_client_fails_at_6_readings_on_no_network_and_heals_under_2_in_the_last_10() -> None:
    client = client_dependency(_AMULED, node_id=_NODE_ID)

    offline = [client.record(rule=CONNECTED_TO_NO_NETWORK, detected=True) for _ in range(6)]
    online = [client.record(rule=CONNECTED_TO_NO_NETWORK, detected=False) for _ in range(9)]

    assert [t and t.current for t in offline] == [*[None] * 5, HealthState.FAILING]
    # The ninth reading on a network leaves a single one on none among the last 10.
    assert [t and t.current for t in online] == [*[None] * 8, HealthState.HEALTHY]


def test_the_client_fails_at_one_refused_password_and_heals_at_the_first_answer() -> None:
    client = client_dependency(_AMULED, node_id=_NODE_ID)

    refused = client.record(rule=PASSWORD_REFUSED, detected=True)
    answered = client.record(rule=PASSWORD_REFUSED, detected=False)

    assert [t and t.current for t in (refused, answered)] == [
        HealthState.FAILING,
        HealthState.HEALTHY,
    ]


def test_a_channel_s_dependency_is_named_after_it_and_holds_both_channel_rules() -> None:
    kad = channel_dependency(client_name=_AMULED, channel=_KAD, node_id=_NODE_ID)
    assert (kad.name, kad.client_name, kad.channel) == ("channel amuled kad", "amuled", "kad")
    # A rule the dependency lacks would raise at its first record.
    assert kad.record(rule=CHANNEL_NOT_CONNECTED, detected=True) is None
    assert kad.record(rule=CHANNEL_NOT_CONNECTABLE, detected=True) is None


def test_a_channel_s_searches_fail_at_3_refused_in_a_row_and_heal_under_2_in_the_last_10() -> None:
    kad = channel_dependency(client_name=_AMULED, channel=_KAD, node_id=_NODE_ID)

    refused = [kad.record(rule=SEARCHES_FAILED, detected=True) for _ in range(3)]
    ran = [kad.record(rule=SEARCHES_FAILED, detected=False) for _ in range(9)]

    assert [t and t.current for t in refused] == [None, None, HealthState.FAILING]
    # The ninth search that ran leaves a single refusal among the last 10.
    assert [t and t.current for t in ran] == [*[None] * 8, HealthState.HEALTHY]


def test_the_client_unreachable_alerts_at_2_min_and_ends_once_reachable_again() -> None:
    client = client_dependency(_AMULED, node_id=_NODE_ID)
    assert _alert_of(client, rule=CLIENT_UNREACHABLE) == HealthAlert(
        when_failing=ClientUnreachableLasting(
            client_name=_AMULED, unreachable_for_seconds=120.0, node_id=_NODE_ID
        ),
        when_healthy_again=ClientReachableAgain(client_name=_AMULED, node_id=_NODE_ID),
    )


def test_a_refused_password_alerts_at_once_and_ends_once_accepted_again() -> None:
    client = client_dependency(_AMULED, node_id=_NODE_ID)
    assert _alert_of(client, rule=PASSWORD_REFUSED) == HealthAlert(
        when_failing=ClientPasswordRefused(client_name=_AMULED, node_id=_NODE_ID),
        when_healthy_again=ClientPasswordAcceptedAgain(client_name=_AMULED, node_id=_NODE_ID),
    )


@pytest.mark.parametrize(
    ("rule", "field"),
    [(CHANNEL_NOT_CONNECTED, "connected"), (CHANNEL_NOT_CONNECTABLE, "connectable")],
)
def test_a_channel_alerts_at_5_min_on_each_rule_of_its_readings_and_ends_once_healthy(
    *, rule: HealthRule, field: ChannelField
) -> None:
    kad = channel_dependency(client_name=_AMULED, channel=_KAD, node_id=_NODE_ID)
    assert _alert_of(kad, rule=rule) == HealthAlert(
        when_failing=ChannelDegraded(
            client_name=_AMULED,
            channel=_KAD,
            field=field,
            degraded_for_seconds=300.0,
            node_id=_NODE_ID,
        ),
        when_healthy_again=ChannelRecovered(
            client_name=_AMULED, channel=_KAD, field=field, node_id=_NODE_ID
        ),
    )


def test_the_client_s_networks_and_a_channel_s_searches_have_no_alert() -> None:
    client = client_dependency(_AMULED, node_id=_NODE_ID)
    kad = channel_dependency(client_name=_AMULED, channel=_KAD, node_id=_NODE_ID)
    assert _alert_of(client, rule=CONNECTED_TO_NO_NETWORK) is None
    assert _alert_of(kad, rule=SEARCHES_FAILED) is None
