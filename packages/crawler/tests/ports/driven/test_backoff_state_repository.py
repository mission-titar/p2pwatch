import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from p2pwatch.ports.driven.backoff_state_repository import (
    BackoffKey,
    BackoffState,
    BackoffStateRepository,
)

_STARTED_AT = datetime(2026, 6, 12, 10, tzinfo=UTC)


class _StubRepository:
    """Satisfies BackoffStateRepository structurally (without importing it)."""

    def __init__(self) -> None:
        self.backoff_state_by_key: dict[BackoffKey, BackoffState] = {}

    def load_backoff_states(self) -> dict[BackoffKey, BackoffState]:
        return dict(self.backoff_state_by_key)

    def save_backoff_states(self, backoff_state_by_key: dict[BackoffKey, BackoffState]) -> None:
        self.backoff_state_by_key = dict(backoff_state_by_key)


def test_a_backoff_key_names_a_channel_or_the_whole_client() -> None:
    channel_key = BackoffKey(client_name="amule-1", channel="kad")
    assert (channel_key.client_name, channel_key.channel) == ("amule-1", "kad")
    assert BackoffKey("amule-1", None) != channel_key
    assert {channel_key: 1}[BackoffKey("amule-1", "kad")] == 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        channel_key.channel = "ed2k"  # type: ignore[misc]


def test_a_backoff_state_is_frozen_and_holds_its_wait() -> None:
    state = BackoffState(attempts=2, started_at=_STARTED_AT, delay=timedelta(seconds=300))
    assert (state.attempts, state.delay) == (2, timedelta(seconds=300))
    assert state.started_at == _STARTED_AT
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.attempts = 3  # type: ignore[misc]


def test_protocol_is_satisfied_structurally() -> None:
    repository: BackoffStateRepository = _StubRepository()
    assert repository.load_backoff_states() == {}
    state = {BackoffKey("amule-1", "kad"): BackoffState(1, _STARTED_AT, timedelta(seconds=2))}
    repository.save_backoff_states(state)
    assert isinstance(repository, _StubRepository)
    assert repository.load_backoff_states() == state
