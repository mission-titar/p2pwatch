import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState, backoff_delay

_STARTED_AT = datetime(2026, 6, 12, 10, tzinfo=UTC)


def test_first_attempt_is_the_base_delay() -> None:
    assert backoff_delay(1, base=2.0, cap=60.0, factor=2.0) == 2.0


def test_delay_grows_exponentially_by_factor() -> None:
    assert backoff_delay(2, base=2.0, cap=60.0, factor=2.0) == 4.0
    assert backoff_delay(3, base=2.0, cap=60.0, factor=2.0) == 8.0
    assert backoff_delay(4, base=2.0, cap=60.0, factor=2.0) == 16.0


def test_delay_is_capped() -> None:
    assert backoff_delay(10, base=2.0, cap=30.0, factor=2.0) == 30.0


def test_base_above_cap_is_also_capped_on_first_attempt() -> None:
    # base > cap: even the first attempt is capped (pathological but safe config).
    assert backoff_delay(1, base=100.0, cap=30.0, factor=2.0) == 30.0


def test_attempt_zero_or_negative_is_treated_as_the_first() -> None:
    assert backoff_delay(0, base=2.0, cap=60.0, factor=2.0) == 2.0
    assert backoff_delay(-5, base=2.0, cap=60.0, factor=2.0) == 2.0


def test_a_backoff_key_names_a_channel_or_the_whole_client() -> None:
    channel_key = BackoffKey(client_name=ClientName("amule-1"), channel=Channel("kad"))
    assert (channel_key.client_name, channel_key.channel) == ("amule-1", "kad")
    assert BackoffKey(ClientName("amule-1"), None) != channel_key
    assert {channel_key: 1}[BackoffKey(ClientName("amule-1"), Channel("kad"))] == 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        channel_key.channel = Channel("ed2k")  # type: ignore[misc]


def test_a_backoff_state_is_frozen_and_holds_its_wait() -> None:
    state = BackoffState(attempts=2, started_at=_STARTED_AT, delay=timedelta(seconds=300))
    assert (state.attempts, state.delay) == (2, timedelta(seconds=300))
    assert state.started_at == _STARTED_AT
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.attempts = 3  # type: ignore[misc]
