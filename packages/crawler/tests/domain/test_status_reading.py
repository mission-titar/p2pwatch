import dataclasses
from datetime import timedelta

import pytest

from p2pwatch.domain.health.health_condition import ConditionWindow, Health
from p2pwatch.domain.health.outcome import Outcome
from p2pwatch.domain.identifiers import Channel
from p2pwatch.domain.status_reading import (
    CLIENT_UNREACHABLE,
    STATUS_API_ANSWER,
    STATUS_PERIOD,
    ChannelStatus,
    ClientNotAnswering,
    ClientStatus,
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


def test_the_client_is_unreachable_at_its_third_unanswered_reading_in_a_row() -> None:
    assert CLIENT_UNREACHABLE.source == STATUS_API_ANSWER
    window = ConditionWindow(condition=CLIENT_UNREACHABLE)
    healths = []
    for _ in range(3):
        window = window.after(Outcome.declared(ClientNotAnswering()))
        healths.append(window.health)
    assert healths == [Health.UNKNOWN, Health.UNKNOWN, Health.FAILING]


def test_a_reading_condition_entering_failing_has_lasted_a_period_per_reading_after_the_first() -> (
    None
):
    # Today's alert, "for 2 min".
    assert lasting_at_entry(CLIENT_UNREACHABLE) == timedelta(minutes=2)
